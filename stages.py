import os
import re
import glob
import json
import shutil
import xml.etree.ElementTree as ET
from PIL import Image

STAGES_DIR = "stages"
OUTPUT_STAGES_DIR = "extractedstages"
OUTPUT_DATA_DIR = "extractedstagesdata"
OUTPUT_CAM_DIR = "extractedstagescameras"

POSITION_DIVISOR = 5

def fnf_to_scratch_x(fnf_x):
    return round((float(fnf_x) - 640.0) / POSITION_DIVISOR, 2)

def fnf_to_scratch_y(fnf_y):
    return round((360.0 - float(fnf_y)) / POSITION_DIVISOR, 2)

def scale_image_by_resolution(img):
    w, h = img.size
    scale_multiplier = 0.5

    new_w = max(1, int(w * scale_multiplier))
    new_h = max(1, int(h * scale_multiplier))

    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def find_asset_files(texture_path):
    norm_path = os.path.normpath(texture_path)
    search_roots = ["images", "shared/images", "shared", "."]
    
    png_path = None
    xml_path = None

    for root_dir in search_roots:
        direct_png = os.path.join(root_dir, f"{norm_path}.png")
        direct_xml = os.path.join(root_dir, f"{norm_path}.xml")

        if not png_path and os.path.exists(direct_png):
            png_path = direct_png
        if not xml_path and os.path.exists(direct_xml):
            xml_path = direct_xml

    if not png_path:
        target_file = os.path.basename(norm_path).lower()
        for root, _, files in os.walk("."):
            for file in files:
                base, ext = os.path.splitext(file)
                if base.lower() == target_file:
                    full_path = os.path.join(root, file)
                    if ext.lower() == ".png" and not png_path:
                        png_path = full_path
                    elif ext.lower() == ".xml" and not xml_path:
                        xml_path = full_path

    return png_path, xml_path

def parse_lua_variables(content):
    vars_dict = {}
    matches = re.findall(r"([a-zA-Z_]\w*)\s*=\s*([-\d.]+)", content)
    for var_name, var_val in matches:
        try:
            vars_dict[var_name] = float(var_val)
        except ValueError:
            pass
    return vars_dict

def safe_eval_coord(expr_str, vars_dict):
    clean_str = expr_str.strip()
    if clean_str in vars_dict:
        return vars_dict[clean_str]
    try:
        return float(eval(clean_str, {"__builtins__": None}, vars_dict))
    except Exception:
        return 0.0

def parse_stage_files(stage_name):
    json_path = os.path.join(STAGES_DIR, f"{stage_name}.json")
    lua_path = os.path.join(STAGES_DIR, f"{stage_name}.lua")
    hx_path = os.path.join(STAGES_DIR, f"{stage_name}.hx")

    bf_pos = [770, 100]
    gf_pos = [400, 130]
    opp_pos = [100, 100]
    zoom = 0.9

    cam_bf = [0, 0]
    cam_gf = [0, 0]
    cam_opp = [0, 0]

    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            bf_pos = data.get("boyfriend", bf_pos)
            gf_pos = data.get("girlfriend", gf_pos)
            opp_pos = data.get("opponent", opp_pos)

            cam_bf = data.get("camera_boyfriend", [0, 0])
            cam_gf = data.get("camera_girlfriend", [0, 0])
            cam_opp = data.get("camera_opponent", [0, 0])

            zoom = data.get("defaultZoom", zoom)
        except Exception as e:
            print(f"  Failed to parse stage JSON for '{stage_name}': {e}")

    cam_data = [
        str(fnf_to_scratch_x(bf_pos[0] + cam_bf[0]) - 50),
        str(fnf_to_scratch_y(bf_pos[1] + cam_bf[1]) - 175),
        "110",
        str(fnf_to_scratch_x(opp_pos[0] + cam_opp[0]) + 50),
        str(fnf_to_scratch_y(opp_pos[1] + cam_opp[1]) - 175),
        "110",
        str(fnf_to_scratch_x(gf_pos[0] + cam_gf[0])),
        str(fnf_to_scratch_y(gf_pos[1] + cam_gf[1]) - 175),
        "100"
    ]

    header_data = [
        f"{{{stage_name}}}",
        str(fnf_to_scratch_x(bf_pos[0])),
        str(fnf_to_scratch_y(bf_pos[1]) - 175),
        "0",
        str(fnf_to_scratch_x(opp_pos[0])),
        str(fnf_to_scratch_y(opp_pos[1]) - 175),
        "0",
        str(fnf_to_scratch_x(gf_pos[0])),
        str(fnf_to_scratch_y(gf_pos[1]) - 175),
        "0",
        str(zoom)
    ]

    sprites = []
    
    if os.path.exists(lua_path):
        with open(lua_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lua_vars = parse_lua_variables(content)

        pattern = r"make(Animated)?LuaSprite\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*([^,]+)\s*,\s*([^,\)]+)\s*\)"
        matches = re.findall(pattern, content)

        layer_counter = 1
        for is_anim, tag, tex_path, x, y in matches:
            fnf_x = safe_eval_coord(x, lua_vars)
            fnf_y = safe_eval_coord(y, lua_vars)

            raw_scale_factor = 1.0
            scale_for_output = 100
            scale_match = re.search(fr"scaleObject\s*\(\s*['\"]{tag}['\"]\s*,\s*([^,]+)\s*,\s*([^\)]+)\s*\)", content)
            if scale_match:
                raw_scale_factor = safe_eval_coord(scale_match.group(1), lua_vars)
                scale_for_output = raw_scale_factor * 80

            png_path, xml_path = find_asset_files(tex_path)
            width, height = 0, 0

            if xml_path and os.path.exists(xml_path):
                try:
                    tree = ET.parse(xml_path)
                    root = tree.getroot()
                    subtex = root.find("SubTexture")
                    if subtex is not None:
                        width = int(subtex.attrib.get("frameWidth", subtex.attrib.get("width", 0)))
                        height = int(subtex.attrib.get("frameHeight", subtex.attrib.get("height", 0)))
                except Exception:
                    pass

            if (width == 0 or height == 0) and png_path and os.path.exists(png_path):
                try:
                    with Image.open(png_path) as img:
                        width, height = img.size
                except Exception:
                    pass

            adjusted_fnf_x = fnf_x + ((width * raw_scale_factor) / 2.0)
            adjusted_fnf_y = fnf_y + ((height * raw_scale_factor) / 2.0)

            scratch_x = fnf_to_scratch_x(adjusted_fnf_x)
            scratch_y = fnf_to_scratch_y(adjusted_fnf_y)

            scroll = 1.0
            scroll_match = re.search(fr"set(?:LuaSprite)?ScrollFactor\s*\(\s*['\"]{tag}['\"]\s*,\s*([-\d.]+)", content)
            if scroll_match:
                scroll = float(scroll_match.group(1))

            fps = 24
            is_loop = True
            anim_prefix = None
            anim_match = re.search(fr"addAnimationByPrefix\s*\(\s*['\"]{tag}['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*([0-9]+)\s*,\s*(true|false)\s*\)", content, re.IGNORECASE)
            if anim_match:
                anim_prefix = anim_match.group(2)
                fps = int(anim_match.group(3))
                is_loop = anim_match.group(4).lower() == "true"

            anim_mode = "constant" if is_loop else "beat"
            engine_speed = max(1, round(fps / 3.5))

            sprites.append({
                "tag": tag,
                "texture": tex_path,
                "x": scratch_x,
                "y": scratch_y,
                "scale": scale_for_output,
                "scroll": scroll,
                "layer": layer_counter,
                "is_animated": 1 if is_anim else 0,
                "anim_mode": anim_mode,
                "speed": engine_speed,
                "anim_prefix": anim_prefix
            })
            layer_counter += 1

    return header_data, sprites, cam_data

def extract_stage_assets(stage_name, sprites):
    extracted_info = {}
    for sprite in sprites:
        tag_key = sprite["tag"]
        texture_name = sprite["texture"]
        png_path, xml_path = find_asset_files(texture_name)

        if not png_path:
            extracted_info[tag_key] = 1
            continue

        base_tex = os.path.basename(os.path.normpath(texture_name))

        if not xml_path:
            out_name = f"{stage_name}_{base_tex}.png"
            out_path = os.path.join(OUTPUT_STAGES_DIR, out_name)
            try:
                with Image.open(png_path) as img:
                    img_resized = scale_image_by_resolution(img)
                    img_resized.save(out_path)
            except Exception:
                pass
            extracted_info[tag_key] = 1
            continue

        try:
            sheet_img = Image.open(png_path).convert("RGBA")
            tree = ET.parse(xml_path)
            root = tree.getroot()

            # Count only UNIQUE animation frames.
            # Some spritesheets contain duplicate SubTexture entries (or the
            # same image with different frameX/frameY/frameWidth/frameHeight).
            # The frame counter must represent the number of distinct images
            # that were actually extracted, not the number of XML entries.
            seen_frames = set()
            frame_idx = 0
            prefix_filter = sprite.get("anim_prefix")

            for subtexture in root.findall("SubTexture"):
                sub_name = subtexture.attrib.get("name", "")
                if prefix_filter and not sub_name.startswith(prefix_filter):
                    continue

                x = int(subtexture.attrib.get("x", 0))
                y = int(subtexture.attrib.get("y", 0))
                width = int(subtexture.attrib.get("width", 0))
                height = int(subtexture.attrib.get("height", 0))

                if width <= 0 or height <= 0:
                    continue

                frame_x = abs(int(subtexture.attrib.get("frameX", 0)))
                frame_y = abs(int(subtexture.attrib.get("frameY", 0)))
                frame_w = int(subtexture.attrib.get("frameWidth", width))
                frame_h = int(subtexture.attrib.get("frameHeight", height))

                cropped_frame = sheet_img.crop((x, y, x + width, y + height))

                canvas_w = max(width, frame_w)
                canvas_h = max(height, frame_h)
                full_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
                full_canvas.paste(cropped_frame, (frame_x, frame_y))

                frame_img = scale_image_by_resolution(full_canvas)

                # Normalize the frame before checking for duplicates.
                # This removes transparent/empty padding differences so that
                # the same visual frame is counted only once.
                bbox = frame_img.getbbox()
                if bbox:
                    normalized_frame = frame_img.crop(bbox)
                else:
                    normalized_frame = frame_img

                frame_key = (
                    normalized_frame.size,
                    normalized_frame.tobytes()
                )

                if frame_key in seen_frames:
                    continue

                seen_frames.add(frame_key)

                if frame_idx == 0:
                    out_filename = f"{stage_name}_{base_tex}.png"
                else:
                    out_filename = f"{stage_name}_{base_tex}_{frame_idx}.png"

                out_path = os.path.join(OUTPUT_STAGES_DIR, out_filename)
                frame_img.save(out_path)
                frame_idx += 1

            # This is the actual number of unique frames extracted.
            # It is no longer a fixed value such as 7.
            extracted_info[tag_key] = max(1, frame_idx)

        except Exception:
            extracted_info[tag_key] = 1

    return extracted_info

def convert_stages():
    if not os.path.exists(STAGES_DIR):
        return

    os.makedirs(OUTPUT_STAGES_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_CAM_DIR, exist_ok=True)

    stage_files = set()
    for f in os.listdir(STAGES_DIR):
        if f.endswith((".json", ".lua", ".hx")):
            stage_files.add(os.path.splitext(f)[0])

    for stage_name in sorted(stage_files):
        header_data, sprites, cam_data = parse_stage_files(stage_name)
        extracted_frames = extract_stage_assets(stage_name, sprites)

        stage_txt_content = list(header_data)

        for s in sprites:
            base_tex = os.path.basename(os.path.normpath(s["texture"]))
            sprite_name = f"{stage_name}_{base_tex}"
            
            if s["is_animated"] == 1:
                frames_count = extracted_frames.get(s["tag"], 1)
            else:
                frames_count = 1

            stage_txt_content.append(sprite_name)
            stage_txt_content.append(str(s["x"]))
            stage_txt_content.append(str(s["y"]))
            stage_txt_content.append(str(s["scale"]))
            stage_txt_content.append(str(s["scroll"]))
            stage_txt_content.append(str(s["layer"]))
            stage_txt_content.append(str(s["is_animated"]))
            stage_txt_content.append(s["anim_mode"])
            # Basic Engine expects animation speed BEFORE total frame count.
            # The previous order was: anim_mode, frame_count, speed,
            # which made the speed value (usually 7) appear as the frame count.
            stage_txt_content.append(str(s["speed"]))
            stage_txt_content.append(str(frames_count))

        with open(os.path.join(OUTPUT_DATA_DIR, f"{stage_name}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(stage_txt_content) + "\n")

        cam_txt_content = [f"{{{stage_name}}}"] + cam_data
        with open(os.path.join(OUTPUT_CAM_DIR, f"{stage_name}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(cam_txt_content) + "\n")

if __name__ == "__main__":
    convert_stages()