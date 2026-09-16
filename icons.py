import os
import json
import glob
from PIL import Image

CHARACTERS_DIR = "characters"
OUTPUT_ICONS_DIR = "extractedicons"

def find_icon_file(health_icon):
    base_icon = health_icon
    if base_icon.lower().startswith("icon-"):
        base_icon = base_icon[5:]

    candidate_names = [
        f"icon-{base_icon}.png",
        f"Icon-{base_icon}.png",
        f"ICON-{base_icon}.png",
        f"{base_icon}.png"
    ]

    search_dirs = [
        os.path.join("images", "icons"),
        "images",
        "icons",
        "."
    ]

    for s_dir in search_dirs:
        for fname in candidate_names:
            full_path = os.path.join(s_dir, fname)
            if os.path.exists(full_path):
                return full_path

    target_lower = f"icon-{base_icon.lower()}.png"
    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue
        for f in os.listdir(s_dir):
            if f.lower() == target_lower:
                return os.path.join(s_dir, f)

    return None

def scale_2x(crop_img):
    w, h = crop_img.size
    return crop_img.resize((w * 2, h * 2), Image.Resampling.NEAREST)

def process_character_icons():
    if not os.path.exists(CHARACTERS_DIR):
        print(f"Directory '{CHARACTERS_DIR}' does not exist.")
        return

    os.makedirs(OUTPUT_ICONS_DIR, exist_ok=True)

    json_files = glob.glob(os.path.join(CHARACTERS_DIR, "*.json"))
    if not json_files:
        print(f"No JSON files found in '{CHARACTERS_DIR}'.")
        return

    for json_path in json_files:
        char_name = os.path.splitext(os.path.basename(json_path))[0]

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Failed to read JSON for '{char_name}': {e}")
            continue

        health_icon = data.get("healthicon", char_name)
        icon_path = find_icon_file(health_icon)

        if not icon_path:
            print(f"[Warning] Could not find icon for character '{char_name}' (healthicon: '{health_icon}')")
            continue

        print(f"Processing icon for '{char_name}': {icon_path}")

        try:
            with Image.open(icon_path) as img:
                width, height = img.size

                if width > 310:
                    part_width = width // 3

                    left_crop = scale_2x(img.crop((0, 0, part_width, height)))
                    left_crop.save(os.path.join(OUTPUT_ICONS_DIR, f"{char_name}_0.png"))

                    mid_crop = scale_2x(img.crop((part_width, 0, part_width * 2, height)))
                    mid_crop.save(os.path.join(OUTPUT_ICONS_DIR, f"{char_name}_1.png"))

                    right_crop = scale_2x(img.crop((part_width * 2, 0, width, height)))
                    right_crop.save(os.path.join(OUTPUT_ICONS_DIR, f"{char_name}_2.png"))

                else:
                    half_width = width // 2

                    left_crop = scale_2x(img.crop((0, 0, half_width, height)))
                    left_crop.save(os.path.join(OUTPUT_ICONS_DIR, f"{char_name}_1.png"))

                    right_crop = scale_2x(img.crop((half_width, 0, width, height)))
                    right_crop.save(os.path.join(OUTPUT_ICONS_DIR, f"{char_name}_0.png"))

        except Exception as e:
            print(f"Failed to split icon image for '{char_name}': {e}")

    print("\nIcon extraction completed successfully.")

if __name__ == "__main__":
    process_character_icons()