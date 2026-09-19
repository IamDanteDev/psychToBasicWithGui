import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from PIL import Image

# 1. Run prerequisite scripts
SCRIPTS_TO_RUN = [
    "weeks.py",
    "characters.py",
    "icons.py",
    "notes.py",
    "noteskins.py",
    "replace.py",
    "songs.py",
    "songsdata.py",
    "stages.py",
]


def run_prerequisite_scripts():
    print("--- Executing Sub-scripts ---")
    for script in SCRIPTS_TO_RUN:
        if os.path.exists(script):
            print(f"Executing {script}...")
            subprocess.run([sys.executable, script], check=True)
    print("--- Sub-scripts Finished ---\n")


def get_file_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def estimate_mp3_duration(file_path):
    try:
        from mutagen.mp3 import MP3

        audio = MP3(file_path)
        return round(audio.info.length, 2)
    except Exception:
        pass

    try:
        size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            data = f.read(10000)

        idx = data.find(b"\xff")
        if idx != -1 and idx + 4 < len(data):
            header = struct.unpack(">I", data[idx : idx + 4])[0]
            bitrate_idx = (header >> 12) & 0xF
            bitrate_map = [
                0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0,
            ]
            bitrate = (
                bitrate_map[bitrate_idx] * 1000
                if bitrate_idx < 16
                else 128000
            )
            if bitrate > 0:
                duration = (size * 8) / bitrate
                return round(duration, 2)
    except Exception:
        pass

    return 180.0


def process_sb3(engine_path=None):
    if engine_path and os.path.isfile(engine_path):
        sb3_input = engine_path
    else:
        sb3_files = glob.glob("*.sb3")
        # Prefer a plain template over earlier built_* outputs so re-runs
        # without an explicit engine stay deterministic.
        templates = [
            f for f in sb3_files
            if not os.path.basename(f).lower().startswith("built_")
        ]
        sb3_files = templates or sb3_files
        if not sb3_files:
            print("No .sb3 file found!")
            return
        sb3_input = sb3_files[0]

    sb3_output = f"built_{os.path.basename(sb3_input)}"
    temp_dir = "_temp_sb3"

    print(f"Engine template: {os.path.basename(sb3_input)}")
    print(f"Unpacking Scratch Project: '{sb3_input}'...")

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    with zipfile.ZipFile(sb3_input, "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    json_path = os.path.join(temp_dir, "project.json")
    with open(json_path, "r", encoding="utf-8") as f:
        project = json.load(f)

    targets = {target["name"]: target for target in project.get("targets", [])}

    # NEVER clear existing list items - always append/extend
    def get_or_create_list(target, list_name):
        for l_id, l_data in target.get("lists", {}).items():
            if l_data[0] == list_name:
                return l_data[1]
        new_id = f"list_{list_name}"
        target.setdefault("lists", {})[new_id] = [list_name, []]
        return target["lists"][new_id][1]

    def add_costume_to_target(target, img_path, prefix=""):
        ext = os.path.splitext(img_path)[1].lower().replace(".", "")
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        costume_name = f"{prefix}{base_name}"

        center_x, center_y = 0, 0
        try:
            with Image.open(img_path) as img:
                w, h = img.size
                center_x = w // 2
                center_y = h // 2
        except Exception:
            pass

        md5 = get_file_md5(img_path)
        filename = f"{md5}.{ext}"

        final_dest = os.path.join(temp_dir, filename)
        if not os.path.exists(final_dest):
            shutil.copy(img_path, final_dest)

        costume_obj = {
            "name": costume_name,
            "bitmapResolution": 2,
            "dataFormat": ext,
            "assetId": md5,
            "md5ext": filename,
            "rotationCenterX": center_x,
            "rotationCenterY": center_y,
        }

        for cost in target["costumes"]:
            if cost["name"] == costume_name:
                target["costumes"].remove(cost)
                break

        target["costumes"].append(costume_obj)

    def add_note_costume_to_target(target, img_path, target_name=""):
        ext = os.path.splitext(img_path)[1].lower().replace(".", "")
        costume_name = os.path.splitext(os.path.basename(img_path))[0]
        costume_lower = costume_name.lower()

        center_x, center_y = 0, 0

        try:
            with Image.open(img_path) as img:
                w, h = img.size
                center_x = w // 2
                center_y = h // 2

                # Apply 200px upward offset when target is Notes//ChartNotes and image contains "holdend"
                if target_name == "Notes//ChartNotes" and "holdend" in costume_lower:
                    center_y -= 200
        except Exception:
            pass

        md5 = get_file_md5(img_path)
        filename = f"{md5}.{ext}"

        final_dest = os.path.join(temp_dir, filename)
        if not os.path.exists(final_dest):
            shutil.copy(img_path, final_dest)

        costume_obj = {
            "name": costume_name,
            "bitmapResolution": 2,
            "dataFormat": ext,
            "assetId": md5,
            "md5ext": filename,
            "rotationCenterX": center_x,
            "rotationCenterY": center_y,
        }

        for cost in target["costumes"]:
            if cost["name"] == costume_name:
                target["costumes"].remove(cost)
                break

        target["costumes"].append(costume_obj)

    def add_sound_to_target(target, audio_path):
        md5 = get_file_md5(audio_path)
        ext = os.path.splitext(audio_path)[1].lower().replace(".", "")
        filename = f"{md5}.{ext}"

        shutil.copy(audio_path, os.path.join(temp_dir, filename))
        sound_name = os.path.splitext(os.path.basename(audio_path))[0]

        sound_obj = {
            "name": sound_name,
            "assetId": md5,
            "dataFormat": ext,
            "format": "",
            "rate": 44100,
            "sampleCount": 0,
            "md5ext": filename,
        }

        for snd in target.get("sounds", []):
            if snd["name"] == sound_name:
                target.get("sounds", []).remove(snd)
                break

        target.setdefault("sounds", []).append(sound_obj)

    # --- 1. Add Sprites ---
    print("\n--- Importing Sprites & Costumes ---")

    if "Game//Characters" in targets:
        char_files = []
        for root, _, files in os.walk("extractedcharacters"):
            for file in files:
                if file.endswith((".png", ".jpg")):
                    char_files.append(os.path.join(root, file))
        
        total_chars = len(char_files)
        print(f"Importing {total_chars} Character costume(s)...")
        for idx, file_p in enumerate(char_files, start=1):
            add_costume_to_target(targets["Game//Characters"], file_p)

    if "Game//Background" in targets:
        bg_files = glob.glob("extractedstages/*.png")
        total_bgs = len(bg_files)
        print(f"Importing {total_bgs} Background stage image(s)...")
        for idx, file_p in enumerate(bg_files, start=1):
            add_costume_to_target(targets["Game//Background"], file_p)

    if "UI//Health/icons" in targets:
        icon_files = glob.glob("extractedicons/*.png")
        total_icons = len(icon_files)
        print(f"Importing {total_icons} Health Icon(s)...")
        for idx, file_p in enumerate(icon_files, start=1):
            add_costume_to_target(targets["UI//Health/icons"], file_p)

    if "Menu//Menu" in targets:
        storymenu_dir = os.path.join("images", "storymenu")
        if os.path.exists(storymenu_dir):
            menu_files = glob.glob(os.path.join(storymenu_dir, "*.png"))
            total_menus = len(menu_files)
            print(f"Importing {total_menus} Story Menu banner(s)...")
            for idx, file_p in enumerate(menu_files, start=1):
                add_costume_to_target(targets["Menu//Menu"], file_p, prefix="week_")

    if "Notes//ChartNotes" in targets:
        notes_dir = "extractednotes"
        if os.path.exists(notes_dir):
            note_files = []
            for root, _, files in os.walk(notes_dir):
                for file in files:
                    if file.endswith((".png", ".jpg")):
                        note_files.append(os.path.join(root, file))
            total_notes = len(note_files)
            print(f"Importing {total_notes} Custom Note asset(s)...")
            for idx, file_p in enumerate(note_files, start=1):
                add_note_costume_to_target(
                    targets["Notes//ChartNotes"], file_p, target_name="Notes//ChartNotes"
                )

    # --- 1b. Add Converted Noteskins ---
    noteskins_dir = "extractednoteskins"
    if os.path.exists(noteskins_dir):
        noteskin_files = glob.glob(os.path.join(noteskins_dir, "*.png"))
        print(f"Importing {len(noteskin_files)} Converted Noteskin costume(s)...")
        for file_p in noteskin_files:
            filename = os.path.basename(file_p)
            parts = filename.split("_", 1)
            
            is_strum = len(parts) > 1 and bool(re.match(r"^\d", parts[1]))
            
            if is_strum and "Notes//StrumNotes" in targets:
                add_note_costume_to_target(
                    targets["Notes//StrumNotes"], file_p, target_name="Notes//StrumNotes"
                )
            elif not is_strum and "Notes//ChartNotes" in targets:
                add_note_costume_to_target(
                    targets["Notes//ChartNotes"], file_p, target_name="Notes//ChartNotes"
                )

    # --- 1c. Add Extracted Splashes to UI//Particles ---
    splashes_dir = "extractedsplashes"
    if os.path.exists(splashes_dir) and "UI//Particles" in targets:
        splash_files = glob.glob(os.path.join(splashes_dir, "*.png"))
        print(f"Importing {len(splash_files)} Splash costume(s) to 'UI//Particles'...")
        for file_p in splash_files:
            add_costume_to_target(targets["UI//Particles"], file_p)

    # --- 1d. Add Replacement Assets from extractedreplace ---
    replace_dir = "extractedreplace"
    if os.path.exists(replace_dir):
        replace_files = [
            f for f in os.listdir(replace_dir)
            if not f.endswith(".txt")
        ]
        print(f"Importing {len(replace_files)} Replacement Asset(s)...")
        for asset_name in replace_files:
            asset_path = os.path.join(replace_dir, asset_name)
            base_name, ext = os.path.splitext(asset_name)
            txt_path = os.path.join(replace_dir, f"{base_name}.txt")

            if not os.path.exists(txt_path):
                print(f"Warning: No mapping TXT found for replacement asset: {asset_name}")
                continue

            with open(txt_path, "r", encoding="utf-8") as f:
                target_sprite_names = [line.strip() for line in f if line.strip()]

            ext_lower = ext.lower()
            for target_name in target_sprite_names:
                if target_name in targets:
                    target_obj = targets[target_name]
                    if ext_lower in [".png", ".jpg", ".jpeg"]:
                        add_costume_to_target(target_obj, asset_path)
                    elif ext_lower in [".mp3", ".wav", ".ogg"]:
                        add_sound_to_target(target_obj, asset_path)
                    print(f"  Replaced/Added asset '{asset_name}' in target '{target_name}'")
                else:
                    print(f"  Warning: Target sprite '{target_name}' not found for asset '{asset_name}'")

    # --- 2. Add Audio ---
    print("\n--- Importing Audio Files ---")
    if "Game//SongPlayer" in targets:
        player_sprite = targets["Game//SongPlayer"]
        audio_files = []
        for root, _, files in os.walk("extractedsongs"):
            for file in files:
                if file.endswith(".mp3"):
                    audio_files.append(os.path.join(root, file))

        total_audio = len(audio_files)
        print(f"Importing {total_audio} Song Audio track(s)...")
        for idx, file_p in enumerate(audio_files, start=1):
            add_sound_to_target(player_sprite, file_p)

    # --- 3. Append to Lists ---
    print("\n--- Generating Project Data Lists ---")
    stage_target = targets.get("Stage", list(targets.values())[0])

    storymode_list = get_or_create_list(stage_target, "📰StoryMode")
    standard_songs = []
    hidden_story_songs = []
    excluded_songs = set()

    if os.path.exists("extractedweeksdata"):
        week_files = sorted(glob.glob("extractedweeksdata/*.txt"))
        total_weeks = len(week_files)
        print(f"Processing {total_weeks} Week file(s)...")

        for idx, txt_file in enumerate(week_files, start=1):
            filename_base = os.path.basename(txt_file)
            if filename_base.lower() == "songorder.txt":
                continue

            with open(txt_file, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()

            is_hide_story = any(line.strip().lower() == "{hidestorymode}" for line in lines)
            is_hide_freeplay = any(line.strip().lower() == "{hidefreeplay}" for line in lines)

            # If it does not contain {hidestorymode}, filter out {hidefreeplay} and append to storymode_list
            if not is_hide_story:
                filtered_lines = [line for line in lines if line.strip().lower() != "{hidefreeplay}"]
                storymode_list.extend(filtered_lines)

            target_song_list = hidden_story_songs if is_hide_story else standard_songs

            for line in lines:
                line_clean = line.strip().lower()
                if line_clean and not (line_clean.startswith("{") and line_clean.endswith("}")):
                    if is_hide_freeplay:
                        excluded_songs.add(line_clean)
                    else:
                        if line_clean not in target_song_list and line_clean not in standard_songs:
                            target_song_list.append(line_clean)

            print(f"  [{idx}/{total_weeks}] Parsed week file: '{filename_base}'")

    # Read defined song order from songorder.txt if present
    song_order_file = os.path.join("extractedweeksdata", "songorder.txt")
    defined_song_order = []
    if os.path.exists(song_order_file):
        with open(song_order_file, "r", encoding="utf-8") as f:
            defined_song_order = [
                line.strip().lower() for line in f if line.strip()
            ]

    ordered_songs = []
    for s in defined_song_order:
        if s not in ordered_songs:
            ordered_songs.append(s)

    for s in standard_songs:
        if s not in ordered_songs:
            ordered_songs.append(s)

    for s in hidden_story_songs:
        if s not in ordered_songs:
            ordered_songs.append(s)

    # Import Custom Notes Data
    custom_notes_list = get_or_create_list(stage_target, "🎵CustomNotes")
    if os.path.exists("extractednotes"):
        c_note_txts = glob.glob("extractednotes/*.txt")
        total_cntxt = len(c_note_txts)
        print(f"Importing {total_cntxt} Custom Note data text file(s)...")
        for idx, txt_file in enumerate(c_note_txts, start=1):
            with open(txt_file, "r", encoding="utf-8") as f:
                custom_notes_list.extend(f.read().splitlines())

    stages_list = get_or_create_list(stage_target, "🏗️Stagesdata")
    other_stages_list = get_or_create_list(stage_target, "🏗️OtherStagesData")

    stage_txts = glob.glob("extractedstagesdata/*.txt")
    total_stg_txt = len(stage_txts)
    print(f"Importing {total_stg_txt} Stage data text file(s)...")

    for idx, txt_file in enumerate(stage_txts, start=1):
        stage_name = os.path.splitext(os.path.basename(txt_file))[0]

        with open(txt_file, "r", encoding="utf-8") as f:
            stages_list.extend(f.read().splitlines())

        cam_txt_file = os.path.join("extractedstagescameras", f"{stage_name}.txt")
        if os.path.exists(cam_txt_file):
            with open(cam_txt_file, "r", encoding="utf-8") as f:
                other_stages_list.extend(f.read().splitlines())
        else:
            other_stages_list.append(f"{{{stage_name}}}")
            other_stages_list.extend(
                ["-100", "0", "120", "100", "0", "120", "0", "50", "110"]
            )

    chars_list = get_or_create_list(stage_target, "🏗️Charactersdata")
    char_txts = glob.glob("extractedcharactersdata/*.txt")
    total_chr_txt = len(char_txts)
    print(f"Importing {total_chr_txt} Character data text file(s)...")

    for idx, txt_file in enumerate(char_txts, start=1):
        with open(txt_file, "r", encoding="utf-8") as f:
            chars_list.extend(f.read().splitlines())

    song_charts = get_or_create_list(stage_target, "📊SongCharts")
    song_events = get_or_create_list(stage_target, "📊SongEvents")
    song_meta = get_or_create_list(stage_target, "📊SongMetadata")
    songs_list = get_or_create_list(stage_target, "📊Songs")
    song_durations = get_or_create_list(stage_target, "📊SongDurations")

    if os.path.exists("extracteddata"):
        all_available_songs = [
            folder for folder in os.listdir("extracteddata")
            if os.path.isdir(os.path.join("extracteddata", folder))
        ]

        for s in all_available_songs:
            s_clean = s.lower()
            if s_clean not in ordered_songs and s_clean not in excluded_songs:
                ordered_songs.append(s_clean)

        valid_song_folders = [s for s in ordered_songs if s not in excluded_songs]
        total_songs = len(valid_song_folders)

        print(f"Adding {total_songs} Song chart(s) and metadata to project lists...")

        for idx, song_folder in enumerate(valid_song_folders, start=1):
            folder_path = os.path.join("extracteddata", song_folder)
            
            if not os.path.exists(folder_path):
                matching_dirs = [
                    f for f in os.listdir("extracteddata")
                    if f.lower() == song_folder.lower()
                ]
                if matching_dirs:
                    folder_path = os.path.join("extracteddata", matching_dirs[0])

            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                songs_list.append(song_folder.lower())

                c_path = os.path.join(folder_path, "chart.txt")
                e_path = os.path.join(folder_path, "events.txt")
                m_path = os.path.join(folder_path, "metadata.txt")

                if os.path.exists(c_path):
                    with open(c_path, "r", encoding="utf-8") as f:
                        song_charts.append(f.read().strip())
                else:
                    song_charts.append("")

                if os.path.exists(e_path):
                    with open(e_path, "r", encoding="utf-8") as f:
                        song_events.append(f.read().strip())
                else:
                    song_events.append("")

                if os.path.exists(m_path):
                    with open(m_path, "r", encoding="utf-8") as f:
                        song_meta.append(f.read().strip())
                else:
                    song_meta.append("")

                duration_found = False
                song_audio_dir = os.path.join("extractedsongs", song_folder)
                
                if not os.path.exists(song_audio_dir) and os.path.exists("extractedsongs"):
                    matching_audio_dirs = [
                        f for f in os.listdir("extractedsongs")
                        if f.lower() == song_folder.lower()
                    ]
                    if matching_audio_dirs:
                        song_audio_dir = os.path.join("extractedsongs", matching_audio_dirs[0])

                if os.path.exists(song_audio_dir):
                    for root, _, files in os.walk(song_audio_dir):
                        for file in files:
                            if file.endswith(".mp3"):
                                audio_p = os.path.join(root, file)
                                dur = estimate_mp3_duration(audio_p)
                                song_durations.append(str(dur))
                                duration_found = True
                                break
                        if duration_found:
                            break

                if not duration_found:
                    song_durations.append("180")

                print(f"  [{idx}/{total_songs}] Added chart & metadata for song: '{song_folder}'")

    # --- Save & Package Output ---
    print("\nSaving updated project.json...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)

    print(f"Building final Scratch project archive: '{sb3_output}'...")
    with zipfile.ZipFile(sb3_output, "w", zipfile.ZIP_DEFLATED) as zip_out:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                full_p = os.path.join(root, file)
                rel_p = os.path.relpath(full_p, temp_dir)
                zip_out.write(full_p, rel_p)

    shutil.rmtree(temp_dir)
    print(f"\nSuccessfully built Scratch project: {sb3_output}")


def main():
    engine = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--engine" and i + 1 < len(args):
            engine = os.path.abspath(args[i + 1])
            i += 2
            continue
        i += 1

    run_prerequisite_scripts()
    process_sb3(engine)


if __name__ == "__main__":
    main()