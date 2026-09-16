import os
import json
import glob
import re
from PIL import Image

WEEKS_DIR = "weeks"
OUTPUT_DIR = "extractedweeksdata"
IMAGE_DIRS = ["images/storymenu", "images", "."]

def parse_lenient_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Try standard JSON first
    try:
        clean_content = re.sub(r',(\s*[\}\]])', r'\1', content)
        return json.loads(clean_content)
    except Exception:
        pass

    # 2. Try json5 if available
    try:
        import json5
        return json5.loads(content)
    except Exception:
        pass

    # 3. Fallback regex fixes for missing commas between array items / strings / brackets
    # Insert missing commas between closing bracket/quote and opening bracket/quote across lines
    fixed = re.sub(r'([\]"}\d])\s*\n\s*([\["{])', r'\1,\n\2', content)
    # Insert missing comma between quoted string and opening bracket on same line
    fixed = re.sub(r'("[^"]+")\s+([\[{])', r'\1, \2', fixed)
    # Remove trailing commas
    fixed = re.sub(r',(\s*[\}\]])', r'\1', fixed)

    return json.loads(fixed)

def scale_image(img_path, dest_path, scale=3.0):
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            resized.save(dest_path)
            print(f"  Scaled image 3x: {os.path.basename(img_path)} -> {dest_path}")
    except Exception as e:
        print(f"  Failed to scale image '{img_path}': {e}")

def convert_psych_weeks():
    if not os.path.exists(WEEKS_DIR):
        print(f"Directory '{WEEKS_DIR}' does not exist.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    json_files = glob.glob(os.path.join(WEEKS_DIR, "*.json"))
    if not json_files:
        print(f"No week JSON files found in '{WEEKS_DIR}'.")
        return

    weeks_data = {}

    for json_path in json_files:
        filename_base = os.path.splitext(os.path.basename(json_path))[0]

        try:
            data = parse_lenient_json(json_path)
        except Exception as e:
            print(f"Failed to read JSON file '{json_path}': {e}")
            continue

        weeks_data[filename_base] = data

        # Format header strictly using the JSON file name in lowercase: e.g. {wiik1}
        output_lines = [f"{{{filename_base.lower()}}}"]

        # Extract song names from the 'songs' array
        # Psych Engine format: "songs": [ ["song-name", "character", [r,g,b]], ... ]
        songs_list = data.get("songs", [])
        for song_entry in songs_list:
            if isinstance(song_entry, list) and len(song_entry) > 0:
                song_title = str(song_entry[0]).lower().replace(" ", "-")
                output_lines.append(song_title)

        # Check for hideFreeplay property
        if data.get("hideFreeplay", False) is True:
            output_lines.append("{hidefreeplay}")

        # Check for hideStoryMode property
        if data.get("hideStoryMode", False) is True:
            output_lines.append("{hidestorymode}")

        # Write output file to extractedweeksdata/<filename_base>.txt
        out_txt_path = os.path.join(OUTPUT_DIR, f"{filename_base}.txt")
        with open(out_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines) + "\n")

        print(f"Converted week: {filename_base} -> {out_txt_path}")

        # Scale week banner/image assets if found
        week_image_name = data.get("weekName", filename_base)
        for img_dir in IMAGE_DIRS:
            if os.path.exists(img_dir):
                for ext in [".png", ".jpg", ".jpeg"]:
                    candidate = os.path.join(img_dir, f"{week_image_name}{ext}")
                    if os.path.exists(candidate):
                        out_img_path = os.path.join(OUTPUT_DIR, f"{filename_base}{ext}")
                        scale_image(candidate, out_img_path, scale=3.0)
                        break

    # Build song order linked list using weekBefore
    sorted_week_keys = []
    remaining_keys = set(weeks_data.keys())

    # Find starting week(s) where weekBefore is empty or not pointing to a known week
    start_keys = [
        k for k in remaining_keys 
        if not weeks_data[k].get("weekBefore") or weeks_data[k].get("weekBefore") not in weeks_data
    ]
    start_keys.sort()

    for start_key in start_keys:
        curr = start_key
        while curr and curr in remaining_keys:
            sorted_week_keys.append(curr)
            remaining_keys.remove(curr)
            # Find next week that has weekBefore == curr
            next_week = None
            for rk in sorted(remaining_keys):
                if weeks_data[rk].get("weekBefore") == curr:
                    next_week = rk
                    break
            curr = next_week

    # Add any leftover unlinked weeks
    for remaining in sorted(remaining_keys):
        sorted_week_keys.append(remaining)

    # Collect song names in ordered list
    ordered_songs = []
    for week_key in sorted_week_keys:
        songs = weeks_data[week_key].get("songs", [])
        for song_entry in songs:
            if isinstance(song_entry, list) and len(song_entry) > 0:
                song_title = str(song_entry[0]).lower().replace(" ", "-")
                ordered_songs.append(song_title)

    # Save ordered songs to songorder.txt in OUTPUT_DIR
    song_order_path = os.path.join(OUTPUT_DIR, "songorder.txt")
    with open(song_order_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ordered_songs) + "\n")

    print(f"Saved song order to: {song_order_path}")
    print("\nWeek conversion completed successfully.")

if __name__ == "__main__":
    convert_psych_weeks()