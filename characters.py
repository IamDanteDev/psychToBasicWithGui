import json
import os
import glob
import colorsys
import hashlib
import re
import math
import xml.etree.ElementTree as ET
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

DATA_DIR = "characters"
OUTPUT_DIR = "extractedcharactersdata"
OUTPUT_FRAMES_DIR = "extractedcharacters"

def scale_image_by_resolution(img):
    w, h = img.size

    if w < 150 or h < 200:
        scale_multiplier = 2
        resample_method = Image.Resampling.NEAREST
    else:
        scale_multiplier = 1.1
        resample_method = Image.Resampling.LANCZOS

    new_w = max(1, int(w * scale_multiplier))
    new_h = max(1, int(h * scale_multiplier))

    return img.resize((new_w, new_h), resample_method)

def get_scratch_color_from_healthbar(colors):
    if not colors or len(colors) < 3:
        return "0"
    
    r, g, b = colors[0] / 255.0, colors[1] / 255.0, colors[2] / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    
    scratch_color = round(h * 200) % 200
    return str(scratch_color)

def get_frame_limit_and_base_name(frame_name, spritesheet_name=""):
    frame_lower = frame_name.lower()
    sheet_lower = spritesheet_name.lower()

    if "dead" not in sheet_lower and "die" not in sheet_lower:
        if re.search(r'\b(dead|dies|retry|gameover|fnf_loss|death)\b', frame_lower):
            return None, 0

    group_name = re.sub(r'\d+$', '', frame_name).strip()

    if any(k in frame_lower for k in ["left", "down", "up", "right"]):
        return group_name, 2

    if any(k in frame_lower for k in ["idle", "dance", "1 instance", "instance"]):
        return group_name, 8

    if any(k in frame_lower for k in ["attack", "dodge"]):
        return group_name, 5

    return group_name, 8

def parse_xml_safely(xml_path):
    if not xml_path or not os.path.exists(xml_path):
        return None
    try:
        with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        content = re.sub(r'<\?xml.*?\?>', '', content, flags=re.DOTALL)
        return ET.fromstring(content.strip())
    except Exception as e:
        print(f"  [Error] Failed parsing XML '{xml_path}': {e}")
        return None

def find_asset_files(image_path_rel):
    clean_rel = image_path_rel.replace("\\", "/")
    base_name = os.path.basename(clean_rel).lower()

    search_dirs = [
        "images/characters",
        "images",
        "characters",
        "."
    ]

    rel_dir = os.path.dirname(clean_rel)
    if rel_dir:
        search_dirs.insert(0, rel_dir)
        search_dirs.insert(0, os.path.join("images", rel_dir))

    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue
        try:
            actual_files = {f.lower(): f for f in os.listdir(s_dir)}
            png_key = f"{base_name}.png"
            xml_key = f"{base_name}.xml"

            if png_key in actual_files and xml_key in actual_files:
                png_path = os.path.join(s_dir, actual_files[png_key])
                xml_path = os.path.join(s_dir, actual_files[xml_key])
                return png_path, xml_path
        except Exception:
            continue

    return None, None

def clean_frame_name(frame_name, json_anim_names):
    if " instance" in frame_name:
        has_instance_in_json = any(" instance" in name for name in json_anim_names)
        if not has_instance_in_json:
            return frame_name.replace(" instance", "")
    return frame_name

def get_xml_frame_names(xml_path):
    root = parse_xml_safely(xml_path)
    if root is None:
        return set()
    return {sub.attrib.get("name") for sub in root.findall("SubTexture") if sub.attrib.get("name")}

def extract_spritesheet_frames(char_name, image_path_rel, json_anim_names, animations=None):
    png_path, xml_path = find_asset_files(image_path_rel)

    if not png_path or not xml_path:
        print(f"  [Warning] Could not find matching PNG/XML for '{image_path_rel}'")
        return

    print(f"  Extracting frames from: {png_path}")

    root = parse_xml_safely(xml_path)
    if root is None:
        return

    spritesheet_name = os.path.basename(image_path_rel)

    dancing_frame_map = {}
    dancing_group_order = {}

    if animations:
        for anim in animations:
            anim_name = anim.get("anim", "")
            costume_name = anim.get("name", "")
            indices = anim.get("indices", [])

            if not indices:
                continue

            if "dancing" in anim_name.lower() or "dancing" in costume_name.lower():
                group_key = (costume_name, anim_name)
                dancing_group_order[group_key] = list(indices)

                for sequence_pos, frame_index in enumerate(indices):
                    try:
                        dancing_frame_map[int(frame_index)] = (group_key, sequence_pos)
                    except (TypeError, ValueError):
                        pass

    try:
        sheet_img = Image.open(png_path)
        os.makedirs(OUTPUT_FRAMES_DIR, exist_ok=True)

        group_min_indices = {}
        subtextures = root.findall("SubTexture")

        for subtexture in subtextures:
            raw_frame_name = subtexture.attrib.get("name")
            if not raw_frame_name:
                continue

            frame_name = clean_frame_name(raw_frame_name, json_anim_names)
            group_name, _ = get_frame_limit_and_base_name(frame_name, spritesheet_name)

            if group_name is None:
                continue

            frame_num_match = re.search(r'(\d+)$', frame_name)
            if frame_num_match and int(frame_num_match.group(1)) in dancing_frame_map:
                dance_group, _ = dancing_frame_map[int(frame_num_match.group(1))]
                if dance_group[0].lower() == group_name.lower():
                    group_name = f"{group_name}|{dance_group[1]}"

            if frame_num_match:
                frame_idx = int(frame_num_match.group(1))
                if group_name not in group_min_indices or frame_idx < group_min_indices[group_name]:
                    group_min_indices[group_name] = frame_idx

        extracted_names = set()
        group_seen_hashes = {}
        anim_group_counts = {}

        for subtexture in subtextures:
            raw_frame_name = subtexture.attrib.get("name")
            if not raw_frame_name:
                continue

            frame_name = clean_frame_name(raw_frame_name, json_anim_names)

            if frame_name in extracted_names:
                continue

            group_name, max_allowed = get_frame_limit_and_base_name(frame_name, spritesheet_name)

            if group_name is None:
                continue

            dance_sequence_pos = None
            frame_num_match = re.search(r'(\d+)$', frame_name)
            if frame_num_match and int(frame_num_match.group(1)) in dancing_frame_map:
                dance_group, dance_sequence_pos = dancing_frame_map[int(frame_num_match.group(1))]
                if dance_group[0].lower() == group_name.lower():
                    group_name = f"{group_name}|{dance_group[1]}"
                    max_allowed = len(dancing_group_order[dance_group])

            current_count = anim_group_counts.get(group_name, 0)
            if current_count >= max_allowed:
                continue

            x = int(float(subtexture.attrib.get("x", 0)))
            y = int(float(subtexture.attrib.get("y", 0)))
            width = int(float(subtexture.attrib.get("width", 0)))
            height = int(float(subtexture.attrib.get("height", 0)))

            # Read un-cropped frame dimensions and offset values
            frame_x = abs(int(float(subtexture.attrib.get("frameX", 0))))
            frame_y = abs(int(float(subtexture.attrib.get("frameY", 0))))
            frame_width = int(float(subtexture.attrib.get("frameWidth", width)))
            frame_height = int(float(subtexture.attrib.get("frameHeight", height)))

            is_rotated = subtexture.attrib.get("rotated", "false").lower() in ("true", "1")

            if width <= 0 or height <= 0:
                continue

            crop_box = (x, y, x + width, y + height)
            cropped_frame = sheet_img.crop(crop_box).copy()

            if is_rotated:
                cropped_frame = cropped_frame.transpose(Image.Transpose.ROTATE_90)

            # Construct full untrimmed frame canvas to preserve original dimensions and relative offset
            frame_img = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
            frame_img.paste(cropped_frame, (frame_x, frame_y))

            img_hash = hashlib.md5(frame_img.tobytes()).hexdigest()

            if group_name not in group_seen_hashes:
                group_seen_hashes[group_name] = set()

            if img_hash in group_seen_hashes[group_name]:
                continue

            group_seen_hashes[group_name].add(img_hash)
            extracted_names.add(frame_name)

            anim_group_counts[group_name] = current_count + 1

            saved_frame_name = frame_name

            if frame_num_match:
                frame_idx = int(frame_num_match.group(1))

                if dance_sequence_pos is not None:
                    dance_group, _ = dancing_frame_map[frame_idx]
                    base_part = re.sub(r'(\d+)$', '', frame_name)

                    if dance_group[1].lower() == "danceright":
                        base_part = re.sub(r'Beat', 'second', base_part, flags=re.IGNORECASE)

                    new_idx = dance_sequence_pos
                else:
                    min_idx = group_min_indices.get(group_name, 0)
                    new_idx = frame_idx - min_idx
                    base_part = re.sub(r'(\d+)$', '', frame_name)
                    base_part = re.sub(r'Beat', 'second', base_part, flags=re.IGNORECASE)

                saved_frame_name = f"{base_part}{new_idx:04d}"

            out_frame_name = f"{char_name}#{saved_frame_name}.png"
            out_frame_path = os.path.join(OUTPUT_FRAMES_DIR, out_frame_name)

            scaled_frame = scale_image_by_resolution(frame_img)
            scaled_frame.save(out_frame_path)

    except Exception as e:
        print(f"  Failed to extract spritesheet frames for {char_name}: {e}")

def process_character(json_path):
    char_name = os.path.splitext(os.path.basename(json_path))[0]

    if char_name.lower() in ["bf", "gf"]:
        print(f"Skipping character: {char_name}")
        return

    out_path = os.path.join(OUTPUT_DIR, f"{char_name}.txt")

    if os.path.getsize(json_path) == 0:
        print(f"  [Warning] Skipping empty JSON file: {json_path}")
        return

    try:
        with open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  [Warning] Skipping corrupt JSON file '{json_path}': {e}")
        return
    except Exception as e:
        print(f"  [Warning] Failed reading '{json_path}': {e}")
        return

    print(f"Processing character: {char_name}")

    json_anim_names = [anim.get("name", "") for anim in data.get("animations", [])]

    raw_image_field = data.get("image", f"characters/{char_name}")
    # Split multi-spritesheet lists separated by commas
    image_rel_paths = [p.strip() for p in raw_image_field.split(",") if p.strip()]

    all_xml_frame_names = set()
    has_dead_sheet = False

    for img_rel in image_rel_paths:
        spritesheet_name = os.path.basename(img_rel)
        sheet_lower = spritesheet_name.lower()
        if "dead" in sheet_lower or "die" in sheet_lower:
            has_dead_sheet = True

        png_path, xml_path = find_asset_files(img_rel)
        if xml_path:
            all_xml_frame_names.update(get_xml_frame_names(xml_path))

        extract_spritesheet_frames(char_name, img_rel, json_anim_names, data.get("animations", []))

    json_scale = data.get("scale", 1.0)
    calculated_size = round(90 * math.sqrt(float(json_scale)))

    lines = [f"{{{char_name}}}", str(calculated_size)]
    
    healthbar_colors = data.get("healthbar_colors", [255, 0, 0])
    lines.append(get_scratch_color_from_healthbar(healthbar_colors))

    for anim in data.get("animations", []):
        anim_name = anim.get("anim", "")
        raw_costume = anim.get("name", "")
        
        anim_lower = anim_name.lower()
        costume_lower = raw_costume.lower()

        if not has_dead_sheet:
            if re.search(r'\b(dead|dies|retry|gameover|fnf_loss|death)\b', anim_lower) or \
               re.search(r'\b(dead|dies|retry|gameover|fnf_loss|death)\b', costume_lower):
                continue

        if anim_name == "danceRight":
            raw_costume = re.sub(r'Beat', 'second', raw_costume, flags=re.IGNORECASE)

        if raw_costume and all_xml_frame_names:
            if raw_costume not in all_xml_frame_names:
                cleaned_costume = re.sub(r'\d+$', '', raw_costume)
                if any(xml_name.startswith(cleaned_costume) for xml_name in all_xml_frame_names):
                    raw_costume = cleaned_costume

        costume_name = f"{char_name}#{raw_costume}" if raw_costume else ""
        
        speed = "1"
        if "dancing" in anim_lower or "dancing beat" in anim_lower or \
           "dancing" in costume_lower or "dancing beat" in costume_lower:
            speed = "2.5"

        lines.extend([
            str(anim_name),
            str(costume_name),
            "0",
            "0",
            speed
        ])
        
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main():
    if not os.path.exists(DATA_DIR):
        print(f"Directory '{DATA_DIR}' not found!")
        return
        
    for json_file in glob.glob(os.path.join(DATA_DIR, "*.json")):
        process_character(json_file)
    print("\nDone! Characters data extracted and spritesheet frames saved successfully.")

if __name__ == "__main__":
    main()