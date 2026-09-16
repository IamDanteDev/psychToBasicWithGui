import os
import re
import glob
import shutil
import hashlib
import xml.etree.ElementTree as ET
from PIL import Image

CUSTOM_NOTES_DIR = "custom_notetypes"
OUTPUT_DIR = "extractednotes"

def scale_and_process_image(img, filename):
    w, h = img.size
    
    # Base scale 4.0x (400%)
    scale_w = 4.0
    scale_h = 4.0
    
    # Extra 300% vertical stretch for hold notes (excluding holdend)
    filename_lower = filename.lower()
    if "_hold_" in filename_lower and "_holdend_" not in filename_lower:
        scale_h *= 3.0

    new_w = max(1, int(w * scale_w))
    new_h = max(1, int(h * scale_h))

    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def parse_note_lua(lua_path):
    with open(lua_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lua_name = os.path.splitext(os.path.basename(lua_path))[0]
    
    # 1. Texture Name Extraction (Handles both setPropertyFromGroup and setProperty calls)
    tex_match = re.search(r"setPropertyFromGroup\s*\(\s*['\"]unspawnNotes['\"]\s*,\s*[^,]+\s*,\s*['\"]texture['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", content)
    if not tex_match:
        tex_match = re.search(r"setProperty\s*\(\s*['\"]unspawnNotes\[[^\]]+\]\.texture['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", content)
    
    texture_name = tex_match.group(1) if tex_match else lua_name

    # 2. Trigger Event Type & Animation
    trigger_type = "hit"
    anim = ""
    
    miss_block = re.search(r"function\s+noteMiss\s*\([^)]*\)(.*?)end", content, re.DOTALL)
    hit_block = re.search(r"function\s+goodNoteHit\s*\([^)]*\)(.*?)end", content, re.DOTALL)

    if miss_block and ("health" in miss_block.group(1).lower() or "addhealth" in miss_block.group(1).lower() or "sethealth" in miss_block.group(1).lower()):
        trigger_type = "miss"
    elif hit_block and ("health" in hit_block.group(1).lower() or "addhealth" in hit_block.group(1).lower() or "sethealth" in hit_block.group(1).lower()):
        trigger_type = "hit"

    anim_match = re.search(r"(?:characterPlayAnim|playAnim)\s*\(\s*['\"](?:boyfriend|player)['\"]\s*,\s*['\"]([^'\"]+)['\"]", content)
    if not anim_match:
        anim_match = re.search(r"(?:characterPlayAnim|playAnim)\s*\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]+)['\"]", content)
    
    if anim_match:
        anim = anim_match.group(1)

    # 3. Health Calculation
    health_delta = 0.0

    # Pattern A: damageValue = curHealth - X
    dmg_match = re.search(r"damageValue\s*=\s*curHealth\s*-\s*([0-9.]+)", content)
    if dmg_match:
        psych_damage = float(dmg_match.group(1))
        health_delta = -round(psych_damage * 100)

    # Pattern B: setHealth(getHealth() - X) or setHealth(getHealth() + X)
    if health_delta == 0.0:
        get_health_sub = re.search(r"setHealth\s*\(\s*getHealth\s*\(\s*\)\s*([+-])\s*([0-9.]+)\s*\)", content)
        if get_health_sub:
            sign = get_health_sub.group(1)
            val = float(get_health_sub.group(2))
            health_delta = -round(val * 100) if sign == "-" else round(val * 100)

    # Pattern C: setProperty('health', X) or addHealth(X)
    if health_delta == 0.0:
        set_health_match = re.search(r"(?:setProperty\s*\(\s*['\"]health['\"]\s*,\s*|addHealth\s*\(\s*)([-\d.]+)", content)
        if set_health_match:
            val = float(set_health_match.group(1))
            health_delta = round(val * 100)

    # Fallback default
    if health_delta == 0.0:
        health_delta = -100 if trigger_type == "miss" else 0

    # 4. Hitbox Milliseconds Threshold
    hitbox_ms = 300
    if trigger_type == "hit" and health_delta < 0:
        hitbox_ms = 150

    return {
        "lua_name": lua_name,
        "texture_name": texture_name,
        "trigger_type": trigger_type,
        "health_delta": int(health_delta),
        "anim": anim,
        "hitbox_ms": hitbox_ms
    }

def classify_subtexture_frame(sub_name):
    sub_lower = sub_name.lower()
    dirs = []

    if "purple" in sub_lower:
        dirs.append("1")
    if "blue" in sub_lower:
        dirs.append("2")
    if "green" in sub_lower:
        dirs.append("3")
    if "red" in sub_lower and "darkred" not in sub_lower:
        dirs.append("4")
    if "white" in sub_lower or "square" in sub_lower or "plus" in sub_lower:
        dirs.append("5")

    if "left" in sub_lower and "1" not in dirs:
        dirs.append("1")
    if "down" in sub_lower and "2" not in dirs:
        dirs.append("2")
    if "up" in sub_lower and "3" not in dirs:
        dirs.append("3")
    if "right" in sub_lower and "darkred" not in sub_lower and "4" not in dirs:
        dirs.append("4")

    if not dirs:
        dirs = ["1", "2", "3", "4"]

    is_hold_end = "end" in sub_lower
    is_hold = "hold" in sub_lower and not is_hold_end

    if is_hold_end:
        type_tag = "holdend"
    elif is_hold:
        type_tag = "hold"
    else:
        type_tag = "tap"

    return dirs, type_tag

def find_asset_files(texture_name):
    norm_tex = os.path.normpath(texture_name)
    tex_dir, tex_file = os.path.split(norm_tex)

    candidate_dirs = [
        "images",
        os.path.join("images", "custom_notetypes"),
        os.path.join("images", "notes"),
        os.path.join("images", tex_dir),
        "."
    ]

    png_path = None
    xml_path = None

    for d in candidate_dirs:
        if not os.path.exists(d):
            continue
        for file in os.listdir(d):
            base, ext = os.path.splitext(file)
            if base.lower() == tex_file.lower():
                full_p = os.path.join(d, file)
                if ext.lower() == ".png" and not png_path:
                    png_path = full_p
                elif ext.lower() == ".xml" and not xml_path:
                    xml_path = full_p

    return png_path, xml_path

def extract_note_spritesheet(lua_name, texture_name):
    png_path, xml_path = find_asset_files(texture_name)

    if not png_path:
        print(f"  [Warning] Could not find PNG image for texture '{texture_name}'")
        return

    if not xml_path:
        try:
            with Image.open(png_path) as img:
                for dir_code in ["1", "2", "3", "4", "5"]:
                    out_name = f"{dir_code}_{lua_name}.png"
                    out_path = os.path.join(OUTPUT_DIR, out_name)
                    processed_img = scale_and_process_image(img, out_name)
                    processed_img.save(out_path)
            print(f"  Extracted static note images for '{lua_name}' (1-5)")
            return
        except Exception as e:
            print(f"  Failed to process static note image '{png_path}': {e}")
            return

    try:
        sheet_img = Image.open(png_path)
        tree = ET.parse(xml_path)
        root = tree.getroot()

        seen_hashes = set()

        for subtexture in root.findall("SubTexture"):
            frame_name = subtexture.attrib.get("name", "")
            if not frame_name:
                continue

            x = int(subtexture.attrib.get("x", 0))
            y = int(subtexture.attrib.get("y", 0))
            width = int(subtexture.attrib.get("width", 0))
            height = int(subtexture.attrib.get("height", 0))

            if width <= 0 or height <= 0:
                continue

            crop_box = (x, y, x + width, y + height)
            frame_img = sheet_img.crop(crop_box)

            dirs, type_tag = classify_subtexture_frame(frame_name)

            for d_code in dirs:
                if type_tag == "tap":
                    out_filename = f"{d_code}_{lua_name}.png"
                else:
                    out_filename = f"{d_code}_{type_tag}_{lua_name}.png"

                unique_key = f"{out_filename}_{hashlib.md5(frame_img.tobytes()).hexdigest()}"
                if unique_key in seen_hashes:
                    continue
                seen_hashes.add(unique_key)

                out_path = os.path.join(OUTPUT_DIR, out_filename)
                
                # Scale image appropriately before saving
                processed_img = scale_and_process_image(frame_img, out_filename)
                processed_img.save(out_path)

        print(f"  Extracted all frames for '{lua_name}' using texture '{texture_name}'")

    except Exception as e:
        print(f"  Failed to extract spritesheet frames for '{lua_name}': {e}")

def convert_custom_notes():
    if not os.path.exists(CUSTOM_NOTES_DIR):
        print(f"Directory '{CUSTOM_NOTES_DIR}' not found!")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    lua_files = glob.glob(os.path.join(CUSTOM_NOTES_DIR, "*.lua"))
    txt_files = glob.glob(os.path.join(CUSTOM_NOTES_DIR, "*.txt"))
    if not lua_files and not txt_files:
        print(f"No custom note .lua or .txt files found in '{CUSTOM_NOTES_DIR}'.")
        return

    for lua_path in lua_files:
        info = parse_note_lua(lua_path)
        lua_name = info["lua_name"]

        print(f"Processing custom note: {lua_name}")

        txt_content = [
            f"{{{lua_name}}}",
            f"{lua_name}",
            f"{info['trigger_type']}",
            f"{info['health_delta']}",
            f"{info['anim']}",
            f"{info['hitbox_ms']}"
        ]

        out_txt_path = os.path.join(OUTPUT_DIR, f"{lua_name}.txt")
        with open(out_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_content) + "\n")

        extract_note_spritesheet(lua_name, info["texture_name"])

    for txt_path in txt_files:
        txt_name = os.path.splitext(os.path.basename(txt_path))[0]

        print(f"Processing default custom note: {txt_name}")

        txt_content = [
            f"{{{txt_name}}}",
            f"{txt_name}",
            "miss",
            "-15",
            "sing",
            "300"
        ]

        out_txt_path = os.path.join(OUTPUT_DIR, f"{txt_name}.txt")
        with open(out_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_content) + "\n")

    print("\nCustom notes conversion completed successfully.")

if __name__ == "__main__":
    convert_custom_notes()