"""Source-engine profile registry for the Psych-to-Basic port tool.

A "source engine profile" describes what a mod folder was made for (Psych
Engine, v-slice base game, ...) so the port pipeline can normalize it into
the Psych layout the extractor scripts expect. Profiles live in
`engines/<id>/engine.json` next to this file; the Psych engine itself is
the virtual default profile and needs no JSON.

Stdlib only.
"""

import json
import os

ENGINES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engines")

# Virtual profile: the current mod folder IS a Psych Engine mod already.
PSYCH_PROFILE = {
    "id": "psych",
    "name": "Psych Engine (current mod folder)",
    "source_root": "",
    "dialect": "psych",
    "psych": True,
}


def list_engines():
    """Return all source-engine profiles, Psych first, never raising."""
    profiles = [dict(PSYCH_PROFILE)]
    if not os.path.isdir(ENGINES_DIR):
        return profiles

    for name in sorted(os.listdir(ENGINES_DIR)):
        profile_path = os.path.join(ENGINES_DIR, name, "engine.json")
        if not os.path.isfile(profile_path):
            continue
        try:
            with open(profile_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if not isinstance(data, dict) or not data.get("id"):
            continue
        data.setdefault("name", data["id"])
        data.setdefault("source_root", "")
        data.setdefault("dialect", "unknown")
        data.setdefault("chart_difficulty_preference", ["normal", "hard", "easy"])
        data["folder"] = os.path.join(ENGINES_DIR, name)
        profiles.append(data)
    return profiles


def get_engine(engine_id):
    """Return one profile by id, or None."""
    if not engine_id:
        return None
    for profile in list_engines():
        if profile.get("id") == engine_id:
            return profile
    return None


def is_psych(profile):
    """True when the profile is the virtual Psych default (no normalization)."""
    return bool(profile and profile.get("psych"))