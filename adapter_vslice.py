"""v-slice (vanilla FNF 0.8.1) source-engine adapter.

Materials a normalized Psych-layout work root from a Base Game / v-slice
engine folder so the EXISTING extractor scripts (weeks.py, characters.py,
stages.py, noteskins.py, icons.py, replace.py, songsdata.py, ...) run
UNCHANGED. The extractors are never modified.

Slice-1 scope (kept as-is):
  - charts  -> translated to the Psych chart-v3 shape (mania 3) and written
               as <song>-canon.json (songsdata.py explicitly prefers -canon)
  - weeks   -> translated to Psych week JSON with a weekBefore chain
  - data/   -> copied (~4.6 MB) then charts translated in place
  - songs/  -> symlinked (POSIX) / junction (Windows) / copied (~445 MB)

Slice-2 scope (added here):
  - images/ -> REAL merged directory (assets/images + shared/images +
               every weekN/images), because translated XML files must land
               in the work root and the extractors must resolve stage and
               character textures without slow tree walks. NOTE_hold_assets
               is excluded (it cannot be consumed as a 4x5 grid).
  - characters -> Psych characters/<name>.json + images/characters/<name>
               .png/.xml (Sparrow). AnimateAtlas-style sheets (Animation.json
               + spritemapN.json) are translated into Sparrow XMLs, flat
               Sparrow pairs are copied verbatim, packer .txt sheets are
               converted to Sparrow XML. Death sheets are renamed so the
               "dead"/"die" sheet rule keeps death frames.
  - stages   -> Psych stages/<name>.json (raw v-slice positions, documented
               caveat) + generated .lua (makeLuaSprite / scaleObject /
               setLuaSpriteScrollFactor / addAnimationByPrefix). Color-fill
               props ("#RRGGBB") are skipped.
  - noteskins -> NOTE_hold_assets -> 4x2 ENDS grid (so noteskins.py emits
               _hold/_holdend), pixel arrows + arrowEndsNew -> pixelUI/
               noteSkins grid pair, noteSplashes -> notesplashes_* copy so
               the splash pipeline works.
  - icons   -> images/icons/icon-*.png ensured as PSYCH strips (2 frames);
               single-frame icons are duplicated into a 2-frame strip with a
               stdlib-only PNG codec.
  - replace -> flat images/healthbar.png, countdown ready/set/go, judgments
               sick/good/bad/shit, num0-9, music/freakyMenu.ogg, sounds/.
- erect/pico charts -> <song>-{erect,pico}-variant.json next to the base
                <song>-canon.json. Variants deliberately avoid the "-canon"
                substring so songsdata.py (which prefers the first *-canon*)
                deterministically picks the BASE chart for story mode.

Stdlib only.
"""

import binascii
import json
import os
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib

SUPPORTED_DIALECTS = ("vslice",)

# Canonical vanilla FNF 0.8.1 week progression. v-slice level files carry no
# order metadata; this list reproduces the story-select order. Unknown weeks
# are appended alphabetically.
CANONICAL_WEEK_ORDER = (
    "tutorial", "week1", "week2", "week3", "week4",
    "week5", "week6", "week7", "weekend1", "sserafim",
)

WEEK_COLOR = [146, 113, 253]  # Psych default purple

# Frames/anim names matching this regex are dropped by the extractor UNLESS
# the image basename contains "dead" or "die". Used to decide death-sheet
# renaming (e.g. "bf-death" -> "bf-dead").
DEATH_RE = re.compile(r"\b(dead|dies|retry|gameover|fnf_loss|death)\b", re.IGNORECASE)

# v-slice characters without a healthIcon field whose icon obviously maps to
# an existing strip (Girlfriend variants, Nene -> her face icon, ...).
HEALTHICON_FALLBACKS = {
    "gf-car": "gf",
    "gf-christmas": "gf",
    "gf-dark": "gf",
    "gf-tankmen": "gf",
    "nene": "face",
    "nene-christmas": "face",
    "nene-dark": "face",
    "nene-tankmen": "face",
    "pico-speaker": "pico",
}

# v-slice sheets reused by gameplay anims whose PREFIX hits the death filter
# while also being needed on non-death anims (bf-holding-gf's singUP reuses
# the death-loop frames). Frame names AND the JSON prefix are renamed so the
# frames survive extraction; both anims keep working.
SHEET_RENAMES = {
    "bfHoldingGF-DEAD": {"BF Dead with GF Loop": "BF Sing with GF Loop"},
}

# Images that must NOT enter the work-root images/ merge because the
# extractors would consume them wrongly (NOTE_hold_assets is translated into
# an ENDS grid instead; the raw 4x1 sheet would be mis-sliced as a 4x5 grid).
SKIP_IMAGEDIR_FILES = {"note_hold_assets.png"}


def _log(msg):
    print(f"[adapter] {msg}")


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception as exc:
        _log(f"Could not read {path}: {exc}")
        return default


def link_or_copy(src, dst):
    """Symlink (POSIX) or junction (Windows) src -> dst; copy as fallback.

    Returns the mechanism actually used: "symlink", "junction", "copy"
    or "existing".
    """
    if os.path.lexists(dst):
        return "existing"
    if os.name == "nt":
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", dst, src],
                check=True,
                capture_output=True,
                text=True,
            )
            return "junction"
        except Exception as exc:
            _log(f"Junction failed for {dst}: {exc}; falling back to copy")
    else:
        try:
            os.symlink(src, dst, target_is_directory=True)
            return "symlink"
        except Exception as exc:
            _log(f"Symlink failed for {dst}: {exc}; falling back to copy")
    shutil.copytree(src, dst)
    return "copy"


def _reset_root(work_root):
    """Remove the previous work root WITHOUT descending into links.

    shutil.rmtree follows junctions on Windows and would delete the real
    song/image content behind a junction, so links are unlinked explicitly
    and only real directories are removed recursively.
    """
    if not os.path.lexists(work_root):
        return
    for name in os.listdir(work_root):
        path = os.path.join(work_root, name)
        if os.path.islink(path) or not os.path.isdir(path):
            try:
                os.unlink(path)
            except OSError:
                os.rmdir(path)  # junction removal
        else:
            shutil.rmtree(path)


def _resolve_source_root(engine_root, profile):
    """Find the folder that holds assets/data (honors profile.source_root)."""
    candidates = []
    src_name = profile.get("source_root") or ""
    if src_name:
        candidates.append(os.path.join(engine_root, src_name))
    candidates.append(engine_root)
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "data")):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Chart translation
# ---------------------------------------------------------------------------

def translate_chart_to_psych(chart_path, metadata_path, out_path, profile):
    """Translate one v-slice chart into Psych chart-v3 format.

    Lanes are remapped (player 4-7 -> 0-3, opponent 0-3 -> 4-7) so
    songsdata.py's Basic-engine output keeps each side on its strum.
    Notes are regrouped into 4-beat sections and events are converted to
    [[ms, [[name, v1, v2]]]].
    """
    chart = _read_json(chart_path)
    if not isinstance(chart, dict):
        raise ValueError(f"Chart is not a JSON object: {chart_path}")

    meta = _read_json(metadata_path, {}) or {}
    play_data = meta.get("playData", {}) or {}
    characters = play_data.get("characters", {}) or {}

    # Difficulty: first existing key from the profile preference list.
    scroll = chart.get("scrollSpeed", {}) or {}
    used_diff = None
    for diff in profile.get("chart_difficulty_preference", ("normal", "hard", "easy")):
        if diff in scroll:
            used_diff = diff
            break
    if used_diff is None:
        keys = list(scroll.keys())
        used_diff = keys[0] if keys else None
    speed = float(scroll.get(used_diff, 1.0)) if used_diff is not None else 1.0

    notes_by_diff = chart.get("notes", {}) or {}
    if used_diff not in notes_by_diff:
        for diff in ("normal", "hard", "easy"):
            if diff in notes_by_diff:
                used_diff = diff
                break
        else:
            used_diff = next(iter(notes_by_diff), "normal")
    raw_notes = notes_by_diff.get(used_diff, []) or []

    # BPM: v-slice charts do not carry it; metadata.timeChanges does.
    time_changes = play_data.get("timeChanges", []) or []
    if not time_changes:
        time_changes = chart.get("timeChanges", []) or []
    bpm = 100.0
    for tc in time_changes:
        if isinstance(tc, dict) and tc.get("bpm"):
            bpm = float(tc["bpm"])
            break
    if bpm == int(bpm):
        bpm = int(bpm)  # Psych charts store whole bpm as ints ({100})

    beat_ms = 60000.0 / bpm
    section_len_ms = 4.0 * beat_ms

    # LANE SEMANTICS (slice 1 - resolved):
    # v-slice encodes lanes 0-3 = opponent, 4-7 = player (bopeebo's opening
    # player riff sits at d=6/7), and the Basic-engine .sb3 puts strums 1-4
    # on the LEFT (enemy) and 5-8 on the RIGHT (BF). songsdata.py's
    # non-legacy branch maps raw 0-3 -> ids 5-8 and 4-7 -> ids 1-4, so a raw
    # passthrough would FLIP sides (player notes land on enemy strums).
    # Therefore lanes are remapped here BEFORE grouping: player lanes 4-7
    # become 0-3 (so songsdata emits BF-side ids 5-8) and opponent lanes 0-3
    # become 4-7 (ids 1-4). must_hit is derived from the ORIGINAL lane.
    sections = {}
    for note in raw_notes:
        if isinstance(note, dict):
            t = note.get("t")
            lane = note.get("d")
            hold = note.get("l", 0) if note.get("l") else 0
        else:
            if not isinstance(note, list) or len(note) < 2:
                continue
            t = note[0]
            lane = note[1]
            hold = note[2] if len(note) > 2 and note[2] else 0
        if t is None or lane is None:
            continue
        t = float(t)
        lane = int(lane)
        idx = int(t // section_len_ms)
        player_side = lane >= 4
        out_lane = lane - 4 if player_side else lane + 4
        sections.setdefault(idx, []).append((t, out_lane, hold, player_side))

    notes_out = []
    for idx in sorted(sections):
        group = sections[idx]
        group.sort()
        must_hit = any(player_side for _t, _lane, _h, player_side in group)
        notes_out.append(
            {
                "mustHitSection": must_hit,
                "sectionNotes": [
                    [int(t), lane, hold] for t, lane, hold, _ps in group
                ],
            }
        )

    # Events -> [[ms, [[name, primary, secondary], ...]], ...]
    # v-slice events appear either as [t, [[e, v1, v2], ...]] or as
    # plain {t, e, v} objects; both are accepted.
    events_out = []
    raw_events = chart.get("events", []) or []
    for evt in raw_events:
        if isinstance(evt, dict):
            t = evt.get("t")
            name = evt.get("e")
            value = evt.get("v")
            if t is None or name is None:
                continue
            subs = []
            subs.append(_format_event_value(str(name), value))
            events_out.append([float(t), subs])
            continue
        if not isinstance(evt, list) or len(evt) < 2:
            continue
        t = float(evt[0])
        subs = []
        for sub in evt[1]:
            if isinstance(sub, dict):
                value = sub.get("v")
                if value is None:
                    continue
                subs.append(_format_event_value(str(sub.get("e", "")), value))
            elif isinstance(sub, list) and len(sub) >= 2:
                subs.append(_format_event_value(str(sub[0]), sub[1]))
        if subs:
            events_out.append([t, subs])

    song_name = os.path.basename(os.path.dirname(out_path))
    out = {
        "song": song_name,
        "bpm": bpm,
        "speed": speed,
        "player1": characters.get("player", "bf") or "bf",
        "player2": characters.get("opponent", "dad") or "dad",
        "gfVersion": characters.get("girlfriend", "gf") or "gf",
        "stage": play_data.get("stage", "stage") or "stage",
        "arrowSkin": "",
        "mania": 3,
        "notes": notes_out,
        "events": events_out,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return {"chart": os.path.basename(out_path), "difficulty": used_diff}


# ---------------------------------------------------------------------------
# Week translation
# ---------------------------------------------------------------------------

def _format_event_value(name, value):
    """Normalize one event value into [name, primary, secondary]."""
    if isinstance(value, dict):
        first_key = sorted(value.keys())[0] if value else ""
        primary = str(value.get(first_key, ""))
        secondary = ""
    elif isinstance(value, list):
        primary = str(value[0]) if value else ""
        secondary = str(value[1]) if len(value) > 1 else ""
    else:
        primary = "" if value is None else str(value)
        secondary = ""
    return [str(name), primary, secondary]


def _opponent_for(song, data_songs_dir):
    meta = _read_json(
        os.path.join(data_songs_dir, song, f"{song}-metadata.json"), {}
    ) or {}
    opponent = (
        (meta.get("playData") or {}).get("characters") or {}
    ).get("opponent")
    return opponent or "dad"


def translate_levels_to_weeks(levels_dir, weeks_out_dir, data_songs_dir):
    """Convert v-slice data/levels/<week>.json -> Psych weeks/<week>.json.

    Returns the list of week basenames written, in story order.
    """
    os.makedirs(weeks_out_dir, exist_ok=True)
    if not os.path.isdir(levels_dir):
        _log(f"No levels dir: {levels_dir}")
        return []

    present = {
        os.path.splitext(f)[0]: f
        for f in os.listdir(levels_dir)
        if f.endswith(".json")
    }
    order = [name for name in CANONICAL_WEEK_ORDER if name in present]
    order += sorted(name for name in present if name not in CANONICAL_WEEK_ORDER)

    written = []
    prev = None
    for name in order:
        data = _read_json(os.path.join(levels_dir, present[name]))
        if not isinstance(data, dict):
            continue
        songs = []
        for entry in data.get("songs", []) or []:
            if isinstance(entry, str):
                song = entry
            elif isinstance(entry, list) and entry:
                song = str(entry[0])
            else:
                continue
            songs.append([song, _opponent_for(song, data_songs_dir), list(WEEK_COLOR)])

        week = {
            "songs": songs,
            "weekName": data.get("name", name),
            "hideFreeplay": False,
            "hideStoryMode": False,
            "weekBefore": prev or "",
        }
        dst = os.path.join(weeks_out_dir, f"{name}.json")
        with open(dst, "w", encoding="utf-8") as fh:
            json.dump(week, fh, indent=2)
        written.append(name)
        prev = name
    return written


# ---------------------------------------------------------------------------
# Slice 2: character sheets
# ---------------------------------------------------------------------------

def _strip_sheet_prefix(asset_path):
    """Split an assetPath reference into (prefix, relpath).

    "shared:characters/bf-death"     -> ("shared", "characters/bf-death")
    "week7:erect/cutscene/tankmanEnding" -> ("week7", "erect/cutscene/...")
    "characters/bfAndGF"             -> ("", "characters/bfAndGF")
    """
    if ":" in asset_path:
        prefix, rel = asset_path.split(":", 1)
        return prefix, rel
    return "", asset_path


def _resolve_sheet_files(source_root, prefix, relpath):
    """Locate a character sheet under the engine source.

    Returns (kind, base) where kind is:
      "atlas"   folder holding Animation.json + spritemap1.json + spritemap1.png
      "sparrow" flat <base>.png + <base>.xml pair
      "packer"  flat <base>.png + <base>.txt pair (Adobe/aseprite packer)
      None      nothing found
    """
    if prefix and prefix.startswith("week"):
        candidates = [os.path.join(source_root, prefix, "images", relpath)]
    else:
        candidates = [
            os.path.join(source_root, "shared", "images", relpath),
            os.path.join(source_root, "images", relpath),
        ]
    for cand in candidates:
        if os.path.isdir(cand) and os.path.isfile(
            os.path.join(cand, "spritemap1.json")
        ) and os.path.isfile(os.path.join(cand, "Animation.json")):
            return "atlas", cand
        if os.path.isfile(cand + ".png"):
            if os.path.isfile(cand + ".xml"):
                return "sparrow", cand
            if os.path.isfile(cand + ".txt"):
                return "packer", cand
    return None, None


def _atlas_labels(anim_json_path):
    """Map top-level timeline labels to frame index intervals.

    Animation.json (Adobe Animate texture-atlas export) carries labels on the
    top-level layer: {N: name, I: start index, DU: frame count}. rando-style
    sheets put no labels on the top layer and come back empty.
    """
    data = _read_json(anim_json_path, {}) or {}
    labels = {}
    timeline = (data.get("AN") or {}).get("TL") or {}
    for layer in timeline.get("L") or []:
        for frame in layer.get("FR") or []:
            name = frame.get("N")
            start = frame.get("I")
            if name is not None and start is not None:
                labels[name] = list(range(int(start), int(start) + int(frame.get("DU", 1))))
    return labels


def _atlas_rects(spritemap_path):
    """Index-ordered crop rectangles from a spritemapN.json."""
    data = _read_json(spritemap_path, {}) or {}
    sprites = (data.get("ATLAS") or {}).get("SPRITES") or []
    rects = []
    for entry in sprites:
        sprite = entry.get("SPRITE") or {}
        rects.append(
            (
                int(sprite.get("x", 0)),
                int(sprite.get("y", 0)),
                int(sprite.get("w", 0)),
                int(sprite.get("h", 0)),
                bool(sprite.get("rotated", False)),
            )
        )
    return rects


def _flatten_sheet_name(relpath):
    """'characters/pico/playable-animations' -> 'pico-playable-animations'."""
    relpath = relpath.replace("\\", "/")
    if relpath.startswith("characters/"):
        relpath = relpath[len("characters/"):]
    name = relpath.replace("/", "-").strip("-")
    return name or "sheet"


def _translated_sheet_name(relpath, death_anims):
    """Death-sheet naming so characters.py keeps death frames.

    The extractor drops frames whose name matches the death regex unless the
    image basename contains 'dead' or 'die'. Sheets used by death anims must
    therefore include that token: 'bf-death' -> 'bf-dead',
    'pico/explosion-death' -> 'pico-explosion-dead', otherwise append '-dead'.
    """
    name = re.sub(r"death", "dead", _flatten_sheet_name(relpath), flags=re.IGNORECASE)
    if death_anims and "dead" not in name.lower() and "die" not in name.lower():
        name += "-dead"
    return name


def _build_sparrow_xml(path, frame_entries, rects, image_name):
    """Write a Sparrow TextureAtlas xml.

    frame_entries: list of (frame_name, rect_index).
    """
    root = ET.Element(
        "TextureAtlas",
        {
            "imagePath": image_name,
            "width": str(max((r[2] for r in rects), default=0)),
            "height": str(max((r[3] for r in rects), default=0)),
        },
    )
    for frame_name, rect_idx in frame_entries:
        if rect_idx is None or rect_idx >= len(rects):
            continue
        x, y, w, h, rotated = rects[rect_idx]
        attrs = {
            "n": frame_name,
            "x": str(x),
            "y": str(y),
            "width": str(w),
            "height": str(h),
            "frameX": "0",
            "frameY": "0",
            "frameWidth": str(w),
            "frameHeight": str(h),
        }
        if rotated:
            attrs["rotated"] = "true"
        ET.SubElement(root, "SubTexture", attrs)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


def _packer_lines_to_frames(txt_path):
    """Parse an FNF packer .txt: '<name> = <x> <y> <w> <h>' per line."""
    frames = []
    try:
        with open(txt_path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if "=" not in line:
                    continue
                name, coords = line.split("=", 1)
                parts = coords.split()
                if len(parts) < 4:
                    continue
                frames.append((name.strip(), tuple(int(p) for p in parts[:4])))
    except Exception as exc:
        _log(f"Could not read packer file {txt_path}: {exc}")
    return frames


def _split_sheet_animations(data, main_rel):
    """Group v-slice animations by sheet reference.

    Returns (sheet_order, sheet_anims) where sheet_anims[key] is the list of
    animations assigned to that sheet and key is (prefix, relpath).
    """
    main_key = None
    if main_rel:
        main_key = _strip_sheet_prefix(main_rel)

    def key_for(anim):
        src = anim.get("assetPath")
        if src:
            return _strip_sheet_prefix(src)
        return main_key

    sheet_order = []
    sheet_anims = {}
    for anim in data.get("animations") or []:
        key = key_for(anim)
        if key is None:
            continue
        if key not in sheet_anims:
            sheet_anims[key] = []
            sheet_order.append(key)
        sheet_anims[key].append(anim)
    return sheet_order, sheet_anims


def _sheet_has_death_anims(anims):
    return any(
        DEATH_RE.search(str(anim.get("name", "")) + " " + str(anim.get("prefix", "")))
        for anim in anims
    )


def _translate_char(data, char_name, source_root, images_out, chars_out):
    """Translate one v-slice character into Psych layout.

    Writes characters/<name>.json + images/characters/<sheet>.png/.xml pairs.
    Returns {"healthicon": id, "sheets": n, "warnings": [..]}.
    """
    main_rel = (data.get("assetPath") or "").strip()
    sheet_order, sheet_anims = _split_sheet_animations(data, main_rel)

    resolved = {}
    for key in sheet_order:
        prefix, relpath = key
        resolved[key] = _resolve_sheet_files(source_root, prefix, relpath)

    images_char_dir = os.path.join(images_out, "characters")
    os.makedirs(images_char_dir, exist_ok=True)

    image_parts = []
    used_display = set()
    warnings = []
    frames_by_key = {}

    for key in sheet_order:
        prefix, relpath = key
        kind, found = resolved[key]
        if kind is None:
            warnings.append(f"{char_name}: sheet '{relpath}' has no assets")
            continue

        anims = sheet_anims[key]
        death_anims = _sheet_has_death_anims(anims)
        display = _translated_sheet_name(relpath, death_anims)
        while display in used_display:
            display += "-2"
        used_display.add(display)

        png_dst = os.path.join(images_char_dir, f"{display}.png")
        xml_dst = os.path.join(images_char_dir, f"{display}.xml")

        if kind == "atlas":
            labels = _atlas_labels(os.path.join(found, "Animation.json"))
            rects = _atlas_rects(os.path.join(found, "spritemap1.json"))
            used_prefixes = set()
            frame_entries = []
            for anim in anims:
                base = anim.get("prefix")
                if not base:
                    continue
                indices = anim.get("frameIndices")
                if not indices:
                    indices = labels.get(base)
                    if not indices:
                        warnings.append(
                            f"{char_name}: anim '{anim.get('name')}' prefix "
                            f"'{base}' has no frames on sheet '{relpath}'"
                        )
                        continue
                frame_base = base
                stem = base
                while frame_base in used_prefixes:
                    stem = f"{base}-{anim.get('name', 'frame')}"
                    frame_base = stem
                used_prefixes.add(frame_base)
                for seq, idx in enumerate(indices):
                    frame_entries.append((f"{frame_base}{seq:04d}", int(idx)))
            if not frame_entries:
                warnings.append(f"{char_name}: sheet '{relpath}' produced no frames")
                continue
            shutil.copy2(os.path.join(found, "spritemap1.png"), png_dst)
            _build_sparrow_xml(xml_dst, frame_entries, rects, f"{display}.png")
        elif kind == "sparrow":
            renames = SHEET_RENAMES.get(relpath) or SHEET_RENAMES.get(display)
            xml_src = found + ".xml"
            with open(xml_src, "r", encoding="utf-8", errors="ignore") as fh:
                xml_text = fh.read()
            if renames:
                for old, new in renames.items():
                    xml_text = re.sub(rf'\b{re.escape(old)}\b', new, xml_text)
            with open(xml_dst, "w", encoding="utf-8") as fh:
                fh.write(xml_text)
            shutil.copy2(found + ".png", png_dst)
        elif kind == "packer":
            frames = _packer_lines_to_frames(found + ".txt")
            if not frames:
                warnings.append(f"{char_name}: packer sheet '{relpath}' is empty")
                continue
            rects = []
            frame_entries = []
            for name, (x, y, w, h) in frames:
                rects.append((x, y, w, h, False))
                frame_entries.append((name, len(rects) - 1))
            shutil.copy2(found + ".png", png_dst)
            _build_sparrow_xml(xml_dst, frame_entries, rects, f"{display}.png")
        else:
            continue

        frames_by_key[key] = display
        image_parts.append(f"characters/{display}")

    # healthicon: v-slice stores it as {"id": ...} or a plain string.
    hi_raw = data.get("healthIcon")
    if isinstance(hi_raw, dict):
        healthicon = hi_raw.get("id") or char_name
    elif isinstance(hi_raw, str) and hi_raw:
        healthicon = hi_raw
    else:
        healthicon = HEALTHICON_FALLBACKS.get(char_name, char_name)

    animations_out = []
    for anim in data.get("animations") or []:
        animations_out.append(
            {
                "anim": anim.get("name", ""),
                "name": anim.get("prefix", ""),
                "indices": anim.get("frameIndices") or [],
            }
        )

    psych = {
        "animations": animations_out,
        "image": ",".join(image_parts),
        "healthicon": healthicon,
    }
    scale = data.get("scale")
    if scale not in (None, 1, 1.0):
        psych["scale"] = scale

    os.makedirs(chars_out, exist_ok=True)
    with open(os.path.join(chars_out, f"{char_name}.json"), "w", encoding="utf-8") as fh:
        json.dump(psych, fh, indent=2)

    return {"healthicon": healthicon, "sheets": len(image_parts), "warnings": warnings}


# ---------------------------------------------------------------------------
# Slice 2: stdlib-only PNG codec (icon strips / hold grids)
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_decode_rgba(path):
    """Decode a non-interlaced 8/16-bit PNG into (w, h, rows).

    rows is a list of bytes, each w*4 big-endian RGBA. Stdlib only.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:8] != _PNG_MAGIC:
        raise ValueError(f"Not a PNG: {path}")
    pos = 8
    ihdr = None
    plte = b""
    trns = b""
    idat = b""
    while pos < len(raw):
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        ctype = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", data)
        elif ctype == b"PLTE":
            plte = data
        elif ctype == b"tRNS":
            trns = data
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
    if ihdr is None:
        raise ValueError(f"No IHDR in PNG: {path}")
    width, height, depth, color, _comp, _filt, interlace = ihdr
    if interlace != 0:
        raise ValueError(f"Interlaced PNG not supported: {path}")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    bytes_per_sample = 2 if depth == 16 else 1
    row_bytes = width * channels * bytes_per_sample
    inflated = zlib.decompress(idat)
    stride = row_bytes + 1
    if len(inflated) < stride * height:
        raise ValueError(f"Truncated PNG data: {path}")
    prev = bytearray(row_bytes)
    rows = []
    for y in range(height):
        filter_type = inflated[y * stride]
        row = bytearray(inflated[y * stride + 1:(y + 1) * stride])
        line = bytearray(row_bytes)
        for i in range(row_bytes):
            a = row[i - bytes_per_sample] if i >= bytes_per_sample else 0
            b = prev[i]
            c = prev[i - bytes_per_sample] if i >= bytes_per_sample else 0
            if filter_type == 0:
                line[i] = row[i]
            elif filter_type == 1:
                line[i] = (row[i] + a) & 0xFF
            elif filter_type == 2:
                line[i] = (row[i] + b) & 0xFF
            elif filter_type == 3:
                line[i] = (row[i] + ((a + b) >> 1)) & 0xFF
            elif filter_type == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (row[i] + pred) & 0xFF
            else:
                raise ValueError(f"Bad PNG filter {filter_type}")
        prev = line
        rows.append(line)
    return width, height, _png_rows_to_rgba(rows, width, channels, depth, plte, trns)


def _png_rows_to_rgba(rows, width, channels, depth, plte, trns):
    out = []
    alpha_override = None
    if plte:
        palette = [tuple(plte[i:i + 3]) for i in range(0, len(plte), 3)]
        if trns:
            alpha_override = list(trns) + [255] * (len(palette) - len(trns))
        else:
            alpha_override = [255] * len(palette)
    for row in rows:
        line = bytearray()
        step = channels * (2 if depth == 16 else 1)
        for i in range(0, len(row), step):
            if depth == 16:
                samples = [row[i + j * 2] for j in range(channels)]
            else:
                samples = [row[i + j] for j in range(channels)]
            if channels == 1:
                v = samples[0]
                if alpha_override is not None:
                    # Palette images: the sample IS the palette index.
                    idx = v if plte else 0
                    a = alpha_override[idx] if idx < len(alpha_override) else 255
                else:
                    a = 255
                line += bytes((v, v, v, a))
            elif channels == 2:
                g, a = samples
                line += bytes((g, g, g, a))
            elif channels == 3:
                line += bytes((*samples, 255))
            else:
                line += bytes(samples)
        out.append(bytes(line))
    return out


def _png_encode_rgba(path, width, height, rows):
    """Encode RGBA8 rows into a flat (filter 0) PNG."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_rows = b"".join(b"\x00" + row for row in rows)
    idat = zlib.compress(raw_rows, 9)
    out = bytearray(_PNG_MAGIC)
    for chunk_type, chunk_data in ((b"IHDR", ihdr), (b"IDAT", idat), (b"IEND", b"")):
        out += struct.pack(">I", len(chunk_data))
        out += chunk_type + chunk_data
        out += struct.pack(">I", zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF)
    with open(path, "wb") as fh:
        fh.write(bytes(out))


def _png_size(path):
    """(width, height) from the IHDR without full decode."""
    with open(path, "rb") as fh:
        head = fh.read(33)
    if len(head) < 24 or head[:8] != _PNG_MAGIC:
        return 0, 0
    return struct.unpack(">II", head[16:24])


def _fabricate_icon_strip(src, dst):
    """Duplicate a single-frame icon into a 2-frame Psych strip."""
    w, h, rows = _png_decode_rgba(src)
    strip_rows = [rows[y] + rows[y] for y in range(h)]
    _png_encode_rgba(dst, w * 2, h, strip_rows)
    return dst


def _fabricate_hold_ends_grid(source_root, images_out):
    """Turn NOTE_hold_assets (4x1 hold pieces) into a 4x2 ENDS grid.

    noteskins.py's pixel-grid path sees a '<name>ENDS.png' 4x2 sheet and
    yields _hold (row 0) and _holdend (row 1) pieces; the row-1 cell reuses
    the hold piece art (v-slice ships no separate end-cap art). The cells are
    upscaled (NEAREST) so the file stays above noteskins.py's 15360-byte
    pixel-art threshold and receives the same non-pixel scaling as the notes.
    """
    src_candidates = [
        os.path.join(source_root, "images", "NOTE_hold_assets.png"),
        os.path.join(source_root, "shared", "images", "NOTE_hold_assets.png"),
    ]
    src = next((p for p in src_candidates if os.path.isfile(p)), None)
    if not src:
        return False
    w, h, rows = _png_decode_rgba(src)
    if w % 4 != 0 or h < 1:
        return False
    cell_w, cell_h = w // 4, h
    scale = 3
    if os.path.getsize(src) > 12000:
        scale = 2
    grid_w, grid_h = cell_w * scale * 4, cell_h * scale * 2
    out_rows = []
    for row_idx in range(2):
        for sy in range(scale):
            for cy in range(cell_h):
                line = bytearray()
                for col in range(4):
                    src_row = rows[cy][col * cell_w * 4:(col + 1) * cell_w * 4]
                    for sx in range(scale):
                        line += src_row
                for _ in range(scale):
                    out_rows.append(bytes(line))
    dst = os.path.join(images_out, "NOTE_hold_assetsENDS.png")
    _png_encode_rgba(dst, grid_w, grid_h, out_rows)
    return os.path.getsize(dst) >= 15360


# ---------------------------------------------------------------------------
# Slice 2: misc provisions
# ---------------------------------------------------------------------------

def _merge_image_tree(src_dir, dst_dir, conflicts, src_label):
    """Copy src_dir into dst_dir; existing files win and are logged."""
    if not os.path.isdir(src_dir):
        return
    for root, dirs, files in os.walk(src_dir):
        if os.path.basename(root) == "characters":
            dirs[:] = []  # atlas folders are inert; flat translations are written separately
            continue
        rel_root = os.path.relpath(root, src_dir)
        for name in files:
            if name.lower() in SKIP_IMAGEDIR_FILES:
                continue
            dst_root = dst_dir if rel_root == "." else os.path.join(dst_dir, rel_root)
            dst = os.path.join(dst_root, name)
            if os.path.exists(dst):
                conflicts.append(f"{src_label}/{rel_root}/{name}")
                continue
            os.makedirs(dst_root, exist_ok=True)
            shutil.copy2(os.path.join(root, name), dst)


def translate_characters(source_root, images_out, chars_out):
    """Translate all v-slice characters; returns summary info."""
    chars_src = os.path.join(source_root, "data", "characters")
    written, skipped, warnings, icon_ids = [], [], [], []
    if not os.path.isdir(chars_src):
        return {"written": written, "skipped": skipped, "warnings": warnings, "icons": icon_ids}
    for fname in sorted(os.listdir(chars_src)):
        if not fname.endswith(".json"):
            continue
        char_name = fname[:-5]
        data = _read_json(os.path.join(chars_src, fname))
        if not isinstance(data, dict) or not data.get("animations"):
            skipped.append((char_name, "no animations"))
            continue
        try:
            info = _translate_char(data, char_name, source_root, images_out, chars_out)
        except Exception as exc:
            skipped.append((char_name, str(exc)))
            _log(f"CHAR TRANSLATION ERROR {char_name}: {exc}")
            continue
        written.append(char_name)
        warnings.extend(info["warnings"])
        icon_ids.append(info["healthicon"])
    return {"written": written, "skipped": skipped, "warnings": warnings, "icons": icon_ids}


def ensure_icon_strips(icon_ids, source_root, images_out):
    """Make every referenced icon a 2-frame Psych strip under images/icons."""
    icons_dir = os.path.join(images_out, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    missing, fabricated, copied = [], [], []
    seen = set()
    for icon_id in sorted(set(icon_ids)):
        if icon_id in seen:
            continue
        seen.add(icon_id)
        src = os.path.join(source_root, "images", "icons", f"icon-{icon_id}.png")
        if not os.path.isfile(src):
            missing.append(icon_id)
            continue
        dst = os.path.join(icons_dir, f"icon-{icon_id}.png")
        w, h = _png_size(src)
        if w >= 2 * h:
            shutil.copy2(src, dst)
            copied.append(icon_id)
        else:
            try:
                _fabricate_icon_strip(src, dst)
                fabricated.append(icon_id)
            except Exception as exc:
                _log(f"ICON FABRICATION FAILED icon-{icon_id}: {exc}")
                missing.append(icon_id)
    return {"missing": missing, "fabricated": fabricated, "copied": copied}


def _stage_lua_number(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def translate_stages(source_root, work_root, images_out):
    """Translate v-slice stages into Psych JSON + generated lua."""
    stages_src = os.path.join(source_root, "data", "stages")
    stages_out = os.path.join(work_root, "stages")
    os.makedirs(stages_out, exist_ok=True)
    written, color_skipped, unresolved, anim_hits = [], 0, [], []

    if not os.path.isdir(stages_src):
        return {
            "written": written, "color_props_skipped": color_skipped,
            "unresolved": unresolved, "animated": anim_hits,
        }

    for fname in sorted(os.listdir(stages_src)):
        if not fname.endswith(".json"):
            continue
        stage_name = fname[:-5]
        data = _read_json(os.path.join(stages_src, fname))
        if not isinstance(data, dict):
            continue

        chars = data.get("characters") or {}
        bf = chars.get("bf") or {}
        opp = chars.get("dad") or {}
        gf = chars.get("gf") or {}
        stage_json = {
            "boyfriend": bf.get("position") or [770, 100],
            "opponent": opp.get("position") or [100, 100],
            "girlfriend": gf.get("position") or [400, 130],
            "camera_boyfriend": bf.get("cameraOffsets") or [0, 0],
            "camera_opponent": opp.get("cameraOffsets") or [0, 0],
            "camera_girlfriend": gf.get("cameraOffsets") or [0, 0],
            "defaultZoom": data.get("cameraZoom", 0.9),
        }
        with open(os.path.join(stages_out, f"{stage_name}.json"), "w", encoding="utf-8") as fh:
            json.dump(stage_json, fh, indent=2)

        lua_lines = []
        animated_here = 0
        for prop in data.get("props") or []:
            tex = prop.get("assetPath")
            if not tex:
                continue
            if tex.startswith("#"):
                color_skipped += 1
                continue
            tag = str(prop.get("name") or tex.replace("/", "_"))
            tag = tag.replace("'", "")
            pos = prop.get("position") or [0, 0]
            scale = (prop.get("scale") or [1, 1])[0]
            scroll = (prop.get("scroll") or [1, 1])[0]
            anims = prop.get("animations") or []

            if anims:
                first = anims[0]
                shape_prefix = first.get("prefix") or first.get("name") or first.get("anim_name")
                anim_name = first.get("name") or first.get("anim_name") or "anim"
                frame_rate = int(first.get("frameRate") or 24)
                looped = bool(first.get("looped", True))
                lua_lines.append(f"makeAnimatedLuaSprite('{tag}', '{tex}', "
                                 f"{_stage_lua_number(pos[0])}, {_stage_lua_number(pos[1])})")
                lua_lines.append(
                    f"addAnimationByPrefix('{tag}', '{anim_name}', '{shape_prefix}', "
                    f"{frame_rate}, {_stage_lua_number(looped)})"
                )
                animated_here += 1
                # Materialize the animated sheet so find_asset_files resolves it.
                _stage_sheet_to_images(source_root, images_out, tex, anims, unresolved)
            else:
                lua_lines.append(f"makeLuaSprite('{tag}', '{tex}', "
                                 f"{_stage_lua_number(pos[0])}, {_stage_lua_number(pos[1])})")
            lua_lines.append(f"scaleObject('{tag}', {_stage_lua_number(scale)}, {_stage_lua_number(scale)})")
            lua_lines.append(f"setLuaSpriteScrollFactor('{tag}', {_stage_lua_number(scroll)}, {_stage_lua_number(scroll)})")

        if lua_lines:
            with open(os.path.join(stages_out, f"{stage_name}.lua"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(lua_lines) + "\n")
        written.append(stage_name)
        if animated_here:
            anim_hits.append((stage_name, animated_here))

    return {
        "written": written, "color_props_skipped": color_skipped,
        "unresolved": unresolved, "animated": anim_hits,
    }


def _stage_sheet_to_images(source_root, images_out, tex, anims, unresolved):
    """Materialize png+xml for an animated stage prop into work images."""
    prefix_kind, relpath = ("", tex)
    if ":" in tex:
        prefix_kind, relpath = tex.split(":", 1)
    kind, found = None, None
    if prefix_kind and prefix_kind.startswith("week"):
        cand = os.path.join(source_root, prefix_kind, "images", relpath)
    else:
        cand = os.path.join(source_root, relpath)
        if not os.path.isdir(cand):
            shared_cand = os.path.join(source_root, "shared", "images", relpath)
            cand = shared_cand if os.path.exists(shared_cand) else cand
    if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "spritemap1.json")):
        kind, found = "atlas", cand
    elif os.path.isfile(cand + ".png"):
        if os.path.isfile(cand + ".xml"):
            kind, found = "sparrow", cand
        elif os.path.isfile(cand + ".txt"):
            kind, found = "packer", cand

    if kind is None:
        unresolved.append(f"{relpath or tex}")
        return

    dst_base = os.path.join(images_out, relpath.replace("\\", "/"))
    os.makedirs(os.path.dirname(dst_base) or images_out, exist_ok=True)

    if kind == "atlas":
        labels = _atlas_labels(os.path.join(found, "Animation.json"))
        rects = _atlas_rects(os.path.join(found, "spritemap1.json"))
        frame_entries = []
        for anim in anims:
            base = anim.get("prefix") or anim.get("name") or ""
            if not base:
                continue
            indices = anim.get("frameIndices")
            if not indices:
                indices = labels.get(base)
                if not indices:
                    unresolved.append(f"{relpath or tex} ({base})")
                    continue
            for seq, idx in enumerate(indices):
                frame_entries.append((f"{base}{seq:04d}", int(idx)))
        if rects:
            shutil.copy2(os.path.join(found, "spritemap1.png"), dst_base + ".png")
            _build_sparrow_xml(dst_base + ".xml", frame_entries, rects, os.path.basename(dst_base) + ".png")
    elif kind == "sparrow":
        shutil.copy2(found + ".png", dst_base + ".png")
        shutil.copy2(found + ".xml", dst_base + ".xml")
    elif kind == "packer":
        frames = _packer_lines_to_frames(found + ".txt")
        if not frames:
            unresolved.append(f"{relpath or tex}")
            return
        for anim in anims:
            base = anim.get("prefix") or anim.get("name") or ""
            indices = anim.get("frameIndices")
            if not indices and base:
                indices = list(range(len(frames)))
            rects = []
            frame_entries = []
            if not indices:
                indices = list(range(len(frames)))
            for seq, idx in enumerate(indices):
                if idx >= len(frames):
                    continue
                name, (x, y, w, h) = frames[idx]
                rects.append((x, y, w, h, False))
                frame_entries.append((f"{base}{seq:04d}", len(rects) - 1))
            if rects:
                shutil.copy2(found + ".png", dst_base + ".png")
                _build_sparrow_xml(dst_base + ".xml", frame_entries, rects, os.path.basename(dst_base) + ".png")


def translate_noteskins(source_root, images_out):
    """Provision the consumable noteskin/splash assets."""
    notes = {"hold_ends": False, "pixel_skin": False, "splash": False}
    notes["hold_ends"] = _fabricate_hold_ends_grid(source_root, images_out)

    # Pixel notes/strums: Psych-style 4x5 grid + 4x2 ENDS sibling.
    pixel_src = os.path.join(source_root, "week6", "images", "weeb", "pixelUI")
    pixel_dst = os.path.join(images_out, "pixelUI", "noteSkins")
    for src_name, dst_name in (("arrows-pixels.png", "arrows-pixels.png"),
                               ("arrowEndsNew.png", "arrows-pixelsENDS.png")):
        src = os.path.join(pixel_src, src_name)
        if os.path.isfile(src):
            os.makedirs(pixel_dst, exist_ok=True)
            shutil.copy2(src, os.path.join(pixel_dst, dst_name))
            notes["pixel_skin"] = True

    # Vanilla note splashes: rename so noteskins.py's notesplashes_ rule hits.
    splash_src = os.path.join(source_root, "shared", "images", "noteSplashes")
    if os.path.isfile(splash_src + ".png") and os.path.isfile(splash_src + ".xml"):
        shutil.copy2(splash_src + ".png", os.path.join(images_out, "noteSplashes_assets.png"))
        shutil.copy2(splash_src + ".xml", os.path.join(images_out, "noteSplashes_assets.xml"))
        notes["splash"] = True

    return notes


def provision_replace_assets(source_root, work_root):
    """Give replace.py every work-root asset it actually consumes."""
    images_out = os.path.join(work_root, "images")
    provided = {"countdown": 0, "judgments": 0, "numbers": 0, "healthbar": False,
                "menu_bg": False, "logo": False, "music_freaky_menu": False}

    def copy_flat(rel_src, rel_dst):
        src = os.path.join(source_root, rel_src)
        dst = os.path.join(work_root, rel_dst)
        if os.path.isfile(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return True
        return False

    for stem in ("ready", "set", "go"):
        if copy_flat(os.path.join("shared", "images", "ui", "countdown", "funkin", f"{stem}.png"),
                     os.path.join("images", f"{stem}.png")):
            provided["countdown"] += 1
    if copy_flat(os.path.join("shared", "images", "healthBar.png"), os.path.join("images", "healthbar.png")):
        provided["healthbar"] = True
    for stem in ("sick", "good", "bad", "shit"):
        if copy_flat(os.path.join("images", "ui", "popup", "funkin", f"{stem}.png"),
                     os.path.join("images", f"{stem}.png")):
            provided["judgments"] += 1
    for i in range(10):
        if copy_flat(os.path.join("images", "ui", "popup", "funkin", f"num{i}.png"),
                     os.path.join("images", f"num{i}.png")):
            provided["numbers"] += 1

    if os.path.isfile(os.path.join(images_out, "menuBG.png")):
        provided["menu_bg"] = True
    if os.path.isfile(os.path.join(images_out, "logoBumpin.png")) and os.path.isfile(
        os.path.join(images_out, "logoBumpin.xml")
    ):
        provided["logo"] = True

    if copy_flat(os.path.join("music", "freakyMenu", "freakyMenu.ogg"),
                 os.path.join("music", "freakyMenu.ogg")):
        provided["music_freaky_menu"] = True

    sounds_src = os.path.join(source_root, "sounds")
    if os.path.isdir(sounds_src):
        link_or_copy(sounds_src, os.path.join(work_root, "sounds"))

    return provided


# ---------------------------------------------------------------------------
# Work-root production
# ---------------------------------------------------------------------------

def apply_engine(engine_root, profile, work_root=None):
    """Build the normalized Psych-layout work root.

    Returns a summary dict, or None when the engine cannot be prepared.
    """
    if profile.get("dialect") not in SUPPORTED_DIALECTS:
        _log(f"Unsupported dialect: {profile.get('dialect')}")
        return None

    source_root = _resolve_source_root(engine_root, profile)
    if source_root is None:
        _log(f"No data/ folder found under: {engine_root}")
        return None

    work_root = work_root or os.path.join(
        engine_root, f".engine_work_{profile['id']}"
    )
    _reset_root(work_root)
    os.makedirs(work_root, exist_ok=True)

    layout = {}
    images_src = os.path.join(source_root, "images")
    images_dst = os.path.join(work_root, "images")
    if os.path.isdir(images_src):
        os.makedirs(images_dst, exist_ok=True)
        conflicts = []
        # assets/images, shared/images, then every weekN/images: first copy
        # wins so assets/images + shared/images beat per-week duplicates.
        _merge_image_tree(images_src, images_dst, conflicts, "assets/images")
        layout["images"] = "merged"
        shared_images = os.path.join(source_root, "shared", "images")
        if os.path.isdir(shared_images):
            _merge_image_tree(shared_images, images_dst, conflicts, "shared/images")
        week_dirs = [
            name for name in sorted(os.listdir(source_root))
            if name not in ("data", "songs", "music", "sounds", "shared", "images")
            and os.path.isdir(os.path.join(source_root, name, "images"))
        ]
        for week in week_dirs:
            _merge_image_tree(
                os.path.join(source_root, week, "images"), images_dst, conflicts, week
            )
        if conflicts:
            _log(f"  image merge conflicts (first copy wins): {len(conflicts)}")
            for c in conflicts[:20]:
                _log(f"    - {c}")
    else:
        _log(f"Missing optional source dir: {images_src}")

    for sub in ("songs",):
        src = os.path.join(source_root, sub)
        if os.path.isdir(src):
            layout[sub] = link_or_copy(src, os.path.join(work_root, sub))
        else:
            _log(f"Missing optional source dir: {src}")

    # data/ is rebuilt as a Psych-layout tree: v-slice nests charts under
    # data/songs/<song>, Psych puts them at data/<song>. The flattened
    # song folders are the only thing songsdata.py should see; the other
    # v-slice data/ subfolders (characters, levels, stages, ...) are
    # translated separately by the slice-2 steps below.
    data_src = os.path.join(source_root, "data")
    data_dst = os.path.join(work_root, "data")
    os.makedirs(data_dst, exist_ok=True)

    songs_src = os.path.join(data_src, "songs")
    translated = 0
    skipped = []
    erect_pico_translated = 0
    if os.path.isdir(songs_src):
        for song in sorted(os.listdir(songs_src)):
            song_path = os.path.join(songs_src, song)
            if not os.path.isdir(song_path):
                continue
            base_charts = [
                f
                for f in os.listdir(song_path)
                if f.endswith("-chart.json")
                and "erect" not in f.lower()
                and "pico" not in f.lower()
            ]
            if not base_charts:
                skipped.append(song)
                continue
            dst_dir = os.path.join(data_dst, song)
            os.makedirs(dst_dir, exist_ok=True)
            meta_path = os.path.join(song_path, f"{song}-metadata.json")
            if os.path.isfile(meta_path):
                shutil.copy2(meta_path, os.path.join(dst_dir, os.path.basename(meta_path)))
            out_path = os.path.join(dst_dir, f"{song}-canon.json")
            try:
                result = translate_chart_to_psych(
                    os.path.join(song_path, base_charts[0]),
                    meta_path,
                    out_path,
                    profile,
                )
                _log(
                    f"Translated {song}: {result['chart']} "
                    f"(difficulty {result['difficulty']})"
                )
                translated += 1
            except Exception as exc:
                _log(f"Chart translation failed for {song}: {exc}")
                skipped.append(song)

            # Slice 2: erect/pico variants -> <song>-{erect,pico}-variant.json.
            # NOT *-canon*: songsdata.py picks the first -canon file it sees,
            # so putting the word "canon" on variants would let a variant win
            # over the base chart at random (os.listdir order).
            for variant, chart_tail, meta_tail in (
                ("erect", "-chart-erect.json", "-metadata-erect.json"),
                ("pico", "-chart-pico.json", "-metadata-pico.json"),
            ):
                chart_path = os.path.join(song_path, f"{song}{chart_tail}")
                if not os.path.isfile(chart_path):
                    continue
                variant_meta = os.path.join(song_path, f"{song}{meta_tail}")
                if not os.path.isfile(variant_meta):
                    variant_meta = os.path.join(song_path, f"{song}{meta_tail.replace('-metadata-', '-')}")
                if not os.path.isfile(variant_meta):
                    variant_meta = meta_path
                out_variant = os.path.join(dst_dir, f"{song}-{variant}-variant.json")
                try:
                    translate_chart_to_psych(chart_path, variant_meta, out_variant, profile)
                    _log(f"Translated {song} ({variant}): {os.path.basename(out_variant)}")
                    erect_pico_translated += 1
                except Exception as exc:
                    _log(f"{variant} chart translation failed for {song}: {exc}")

    weeks = translate_levels_to_weeks(
        os.path.join(data_src, "levels"),
        os.path.join(work_root, "weeks"),
        songs_src,
    )

    # ---- Slice 2: characters + icons -------------------------------
    chars_out = os.path.join(work_root, "characters")
    char_info = translate_characters(source_root, images_dst, chars_out)
    icon_info = ensure_icon_strips(char_info["icons"], source_root, images_dst)

    # ---- Slice 2: stages -------------------------------------------
    stage_info = translate_stages(source_root, work_root, images_dst)

    # ---- Slice 2: noteskins + splashes -------------------------------
    noteskin_info = translate_noteskins(source_root, images_dst)

    # ---- Slice 2: replace assets --------------------------------------
    replace_info = provision_replace_assets(source_root, work_root)

    summary = {
        "work_root": work_root,
        "source_root": source_root,
        "layout": layout,
        "charts_translated": translated,
        "charts_skipped": skipped,
        "erect_pico_translated": erect_pico_translated,
        "weeks": weeks,
        "characters": char_info,
        "icons": icon_info,
        "stages": stage_info,
        "noteskins": noteskin_info,
        "replace": replace_info,
    }
    _log(f"Work root ready: {work_root}")
    _log(f"  layout        : {layout}")
    _log(f"  charts        : {translated} translated, {len(skipped)} skipped")
    _log(f"  erect/pico    : {erect_pico_translated} variant charts translated")
    _log(f"  weeks         : {len(weeks)} ({', '.join(weeks)})")
    _log(f"  characters    : {len(char_info['written'])} translated, "
         f"{len(char_info['skipped'])} skipped")
    _log(f"  icons         : {len(icon_info['copied'])} copied, "
         f"{len(icon_info['fabricated'])} fabricated, "
         f"{len(icon_info['missing'])} missing")
    _log(f"  stages        : {len(stage_info['written'])} translated "
         f"({stage_info['color_props_skipped']} color props skipped, "
         f"{len(stage_info['animated'])} animated)")
    _log(f"  noteskins     : hold-ends={noteskin_info['hold_ends']} "
         f"pixel={noteskin_info['pixel_skin']} splash={noteskin_info['splash']}")
    _log(f"  replace       : {replace_info}")
    if char_info["warnings"]:
        _log(f"  char warnings : {len(char_info['warnings'])}")
        for warn in char_info["warnings"][:12]:
            _log(f"    - {warn}")
    if skipped:
        _log(f"  skipped songs : {', '.join(skipped)}")
    return summary