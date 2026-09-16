import os
import re
import xml.etree.ElementTree as ET
import colorsys
from PIL import Image

# Target primary colors to detect and remap dynamically
KEY_COLORS = {
    "red": (254, 0, 0),     # #FE0000
    "green": (0, 255, 0),   # #00FF00
    "blue": (0, 0, 253)     # #0000FD
}

# Dynamic Mappings per note direction
COLOR_MAPS = {
    "1": { "red": "#BF4D93", "green": "#FFFFFD", "blue": "#412258" }, # Left
    "2": { "red": "#0BFBFF", "green": "#FFFFFD", "blue": "#1C41B1" }, # Down
    "3": { "red": "#27F510", "green": "#FFFFFD", "blue": "#0A454D" }, # Up
    "4": { "red": "#F53439", "green": "#FFFFFD", "blue": "#600E37" }  # Right
}

# Exact static color replacements per note direction
EXACT_COLOR_MAPS = {
    "1": { "#794849": "#7F6DB2", "#BD7683": "#8C7BBA" }, # Left
    "2": { "#794849": "#58B6BE", "#BD7683": "#72C0C7" }, # Down
    "3": { "#794849": "#5CBF7A", "#BD7683": "#70C88C" }, # Up
    "4": { "#794849": "#B66977", "#BD7683": "#BC7783" }  # Right
}

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def adjust_brightness(base_rgb, multiplier):
    r, g, b = base_rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    new_v = min(1.0, max(0.0, v * multiplier))
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, new_v)
    return int(nr * 255), int(ng * 255), int(nb * 255)

def remap_image_colors(img, note_num):
    img = img.convert("RGBA")
    pixels = img.load()
    w, h = img.size

    exact_map = EXACT_COLOR_MAPS.get(note_num, {})
    exact_rgb_map = {hex_to_rgb(k): hex_to_rgb(v) for k, v in exact_map.items()}

    for x in range(w):
        for y in range(h):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if (r, g, b) in exact_rgb_map:
                nr, ng, nb = exact_rgb_map[(r, g, b)]
                pixels[x, y] = (nr, ng, nb, a)

    if note_num not in COLOR_MAPS:
        return img

    found_colors = {"red": False, "green": False, "blue": False}

    for x in range(w):
        for y in range(h):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            for key, (tr, tg, tb) in KEY_COLORS.items():
                if abs(r - tr) <= 30 and abs(g - tg) <= 30 and abs(b - tb) <= 30:
                    found_colors[key] = True

    if not (found_colors["red"] and found_colors["green"] and found_colors["blue"]):
        return img

    mapping = COLOR_MAPS[note_num]
    target_rgbs = {k: hex_to_rgb(v) for k, v in mapping.items()}

    for x in range(w):
        for y in range(h):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue

            matched_key = None
            if r > g and r > b:
                matched_key = "red"
            elif g > r and g > b:
                matched_key = "green"
            elif b > r and b > g:
                matched_key = "blue"

            if matched_key:
                orig_target = KEY_COLORS[matched_key]
                orig_max = max(orig_target)
                current_max = max(r, g, b)
                brightness_multiplier = current_max / orig_max if orig_max > 0 else 1.0

                new_base_rgb = target_rgbs[matched_key]
                new_r, new_g, new_b = adjust_brightness(new_base_rgb, brightness_multiplier)
                pixels[x, y] = (new_r, new_g, new_b, a)

    return img

def get_noteskin_name(file_base):
    clean_base = re.sub(r'^(splash_|notesplashes_)', '', file_base, flags=re.IGNORECASE)
    clean_base = re.sub(r'ENDS$', '', clean_base, flags=re.IGNORECASE)
    clean_base = re.sub(r'NOTE', '', clean_base, flags=re.IGNORECASE)
    clean_base = re.sub(r'_?assets', '', clean_base, flags=re.IGNORECASE)
    clean_base = clean_base.strip('_')
    
    if not clean_base:
        return ""
    return f"_{clean_base}"

def apply_fixed_scale(crop_img, scale_factor, is_pixel_art, variant=""):
    w, h = crop_img.size
    if w <= 0 or h <= 0:
        return crop_img

    resample = Image.Resampling.NEAREST if is_pixel_art else Image.Resampling.LANCZOS
    
    scaled_w = int(w * scale_factor)
    scaled_h = int(h * scale_factor)
    scaled_img = crop_img.resize((scaled_w, scaled_h), resample) if scale_factor != 1 else crop_img

    canvas_w = scaled_w * 2
    canvas_h = scaled_h * 2
    
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    paste_x = (canvas_w - scaled_w) // 2
    paste_y = (canvas_h - scaled_h) // 2

    canvas.paste(scaled_img, (paste_x, paste_y))
    
    return canvas

def process_splash_file(png_path, xml_path, base_name, splash_output_dir):
    noteskin_suffix = get_noteskin_name(base_name)
    try:
        atlas_img = Image.open(png_path)
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Error loading splash file {base_name}: {e}")
        return

    frames = []
    seen_crops = set()

    for subtexture in root.findall("SubTexture"):
        frame_name = subtexture.attrib.get("name", "").lower()
        if "red" not in frame_name:
            continue

        x = int(subtexture.attrib.get("x", 0))
        y = int(subtexture.attrib.get("y", 0))
        w = int(subtexture.attrib.get("width", 0))
        h = int(subtexture.attrib.get("height", 0))
        crop_bounds = (x, y, x + w, y + h)

        if crop_bounds not in seen_crops:
            seen_crops.add(crop_bounds)
            frames.append(crop_bounds)
            if len(frames) == 4:
                break

    for idx, crop_bounds in enumerate(frames, start=1):
        crop_img = atlas_img.crop(crop_bounds)
        is_pixel = os.path.getsize(png_path) < 15360
        padded_img = apply_fixed_scale(crop_img, 1.2, is_pixel)

        out_filename = f"splash{idx}{noteskin_suffix}.png"
        padded_img.save(os.path.join(splash_output_dir, out_filename))
        print(f"Saved Splash Frame: {out_filename}")

def slice_pixel_grid_sheet(png_path, noteskin_suffix, output_dir, processed_outputs, scale_factor, is_pixel_art):
    try:
        sheet = Image.open(png_path).convert("RGBA")
    except Exception as e:
        print(f"Error opening pixel sheet {png_path}: {e}")
        return

    sheet_w, sheet_h = sheet.size

    if png_path.lower().endswith("ends.png"):
        cols, rows = 4, 2 if sheet_h >= 2 else 1
        cell_w, cell_h = sheet_w // cols, sheet_h // rows
        ends_mapping = [
            (0, 0, "1", "_hold"),    (0, 1, "2", "_hold"),    (0, 2, "3", "_hold"),    (0, 3, "4", "_hold"),
            (rows-1, 0, "1", "_holdend"), (rows-1, 1, "2", "_holdend"), (rows-1, 2, "3", "_holdend"), (rows-1, 3, "4", "_holdend"),
        ]
        for row, col, num, variant in ends_mapping:
            if (num, variant) in processed_outputs:
                continue
            x1, y1 = col * cell_w, row * cell_h
            crop_img = sheet.crop((x1, y1, x1 + cell_w, y1 + cell_h))
            crop_img = remap_image_colors(crop_img, num)
            
            resample = Image.Resampling.NEAREST if is_pixel_art else Image.Resampling.LANCZOS

            if variant == "_hold":
                w, h = crop_img.size
                crop_img = crop_img.resize((w, h * 3), resample)

            padded_img = apply_fixed_scale(crop_img, scale_factor, is_pixel_art, variant=variant)

            out_filename = f"{num}{variant}{noteskin_suffix}.png"
            padded_img.save(os.path.join(output_dir, out_filename))
            processed_outputs.add((num, variant))
            print(f"Saved (Ends Sheet): {out_filename}")
        return

    ends_path = re.sub(r'\.png$', 'ENDS.png', png_path, flags=re.IGNORECASE)
    if os.path.exists(ends_path):
        slice_pixel_grid_sheet(ends_path, noteskin_suffix, output_dir, processed_outputs, scale_factor, is_pixel_art)

    cols, rows = 4, 5
    cell_w, cell_h = sheet_w // cols, sheet_h // rows

    mapping = [
        (0, 0, "1", ["_0"]), (0, 1, "2", ["_0"]), (0, 2, "3", ["_0"]), (0, 3, "4", ["_0"]),
        (1, 0, "1", [""]),   (1, 1, "2", [""]),   (1, 2, "3", [""]),   (1, 3, "4", [""]),
        (2, 0, "1", ["_4", "_5"]), (2, 1, "2", ["_4", "_5"]), (2, 2, "3", ["_4", "_5"]), (2, 3, "4", ["_4", "_5"]),
        (3, 0, "1", ["_3"]), (3, 1, "2", ["_3"]), (3, 2, "3", ["_3"]), (3, 3, "4", ["_3"]),
        (4, 0, "1", ["_2", "_1"]), (4, 1, "2", ["_2", "_1"]), (4, 2, "3", ["_2", "_1"]), (4, 3, "4", ["_2", "_1"]),
    ]

    for row, col, num, variants in mapping:
        x1, y1 = col * cell_w, row * cell_h
        crop_img = sheet.crop((x1, y1, x1 + cell_w, y1 + cell_h))
        crop_img = remap_image_colors(crop_img, num)

        for variant in variants:
            if (num, variant) in processed_outputs:
                continue
            padded_img = apply_fixed_scale(crop_img, scale_factor, is_pixel_art, variant=variant)
            out_filename = f"{num}{variant}{noteskin_suffix}.png"
            padded_img.save(os.path.join(output_dir, out_filename))
            processed_outputs.add((num, variant))
            print(f"Saved (Pixel Grid): {out_filename}")

def process_noteskins():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(script_dir, "images")
    
    input_dirs = [
        os.path.join(images_dir, "pixelUI", "noteSkins"),
        os.path.join(images_dir, "noteSkins"),
        os.path.join(images_dir, "HUD"),
        os.path.join(images_dir, "hud"),
        images_dir
    ]
    output_dir = os.path.join(script_dir, "extractednoteskins")
    splash_output_dir = os.path.join(script_dir, "extractedsplashes")
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(splash_output_dir, exist_ok=True)

    for input_dir in input_dirs:
        if not os.path.exists(input_dir):
            continue

        for file in os.listdir(input_dir):
            if not file.endswith(".png"):
                continue

            base_name = os.path.splitext(file)[0]
            png_path = os.path.join(input_dir, file)
            xml_path = os.path.join(input_dir, base_name + ".xml")

            if ("splash_" in base_name.lower() or "notesplashes_" in base_name.lower()) and os.path.exists(xml_path):
                process_splash_file(png_path, xml_path, base_name, splash_output_dir)
                continue

            if (input_dir == images_dir or "hud" in input_dir.lower()) and "note" not in file.lower():
                continue

            if base_name.lower().endswith("ends"):
                main_base = re.sub(r'ENDS$', '', base_name, flags=re.IGNORECASE)
                if os.path.exists(os.path.join(input_dir, main_base + ".png")):
                    continue

            noteskin_suffix = get_noteskin_name(base_name)
            processed_outputs = set()

            is_pixel_art = ("pixelUI" in input_dir) or (os.path.getsize(png_path) < 15360)
            
            scale_factor = 36 if is_pixel_art else 4
            resampling_method = Image.Resampling.NEAREST if is_pixel_art else Image.Resampling.LANCZOS

            if not os.path.exists(xml_path):
                slice_pixel_grid_sheet(png_path, noteskin_suffix, output_dir, processed_outputs, scale_factor, is_pixel_art)
                continue

            try:
                atlas_img = Image.open(png_path)
                tree = ET.parse(xml_path)
                root = tree.getroot()
            except Exception as e:
                print(f"Error loading {base_name}: {e}")
                continue

            press_crops_by_key = { "1": [], "2": [], "3": [], "4": [], "5": [] }

            for subtexture in root.findall("SubTexture"):
                frame_name = subtexture.attrib.get("name", "").lower()
                if "press" not in frame_name:
                    continue

                num = None
                if re.search(r"^(arrowleft|purple|pruple|left confirm|left press)", frame_name):
                    num = "1"
                elif re.search(r"^(arrowdown|blue|down confirm|down press)", frame_name):
                    num = "2"
                elif re.search(r"^(arrowup|green|up confirm|up press)", frame_name):
                    num = "3"
                elif re.search(r"^(arrowright|red|right confirm|right press)", frame_name):
                    num = "4"
                elif frame_name.startswith("square"):
                    num = "5"

                if num:
                    x = int(subtexture.attrib.get("x", 0))
                    y = int(subtexture.attrib.get("y", 0))
                    w = int(subtexture.attrib.get("width", 0))
                    h = int(subtexture.attrib.get("height", 0))
                    crop_bounds = (x, y, x + w, y + h)

                    if crop_bounds not in press_crops_by_key[num]:
                        press_crops_by_key[num].append(crop_bounds)

            for subtexture in root.findall("SubTexture"):
                frame_name = subtexture.attrib.get("name", "").lower()
                x = int(subtexture.attrib.get("x", 0))
                y = int(subtexture.attrib.get("y", 0))
                w = int(subtexture.attrib.get("width", 0))
                h = int(subtexture.attrib.get("height", 0))

                crop_bounds = (x, y, x + w, y + h)

                num = None
                if re.search(r"^(arrowleft|purple|pruple|left confirm|left press)", frame_name):
                    num = "1"
                elif re.search(r"^(arrowdown|blue|down confirm|down press)", frame_name):
                    num = "2"
                elif re.search(r"^(arrowup|green|up confirm|up press)", frame_name):
                    num = "3"
                elif re.search(r"^(arrowright|red|right confirm|right press)", frame_name):
                    num = "4"
                elif frame_name.startswith("square"):
                    num = "5"
                else:
                    continue

                frame_match = re.search(r"(\d+)$", frame_name)
                frame_idx = int(frame_match.group(1)) if frame_match else 0

                variants = []
                if "arrow" in frame_name or "static" in frame_name:
                    variants = ["_0"]
                elif frame_name.startswith(("purple0000", "pruple0000", "blue0000", "green0000", "red0000", "square0000")):
                    variants = [""]
                elif "confirm" in frame_name:
                    if frame_idx >= 3:
                        continue
                    variants = [f"_{3 - frame_idx}"]
                elif "press" in frame_name:
                    distinct_presses = press_crops_by_key.get(num, [])
                    if crop_bounds in distinct_presses:
                        idx = distinct_presses.index(crop_bounds)
                        if idx == 0:
                            variants = ["_4"]
                        elif idx == 1:
                            variants = ["_5"]
                        else:
                            continue
                    else:
                        continue
                elif "end" in frame_name:
                    variants = ["_holdend"]
                elif "hold" in frame_name:
                    variants = ["_hold"]
                else:
                    continue

                unprocessed_variants = [v for v in variants if (num, v) not in processed_outputs]
                if not unprocessed_variants:
                    continue

                crop_img = atlas_img.crop(crop_bounds)
                crop_img = remap_image_colors(crop_img, num)

                is_regular_hold = "hold" in frame_name and "end" not in frame_name
                if is_regular_hold:
                    crop_img = crop_img.resize((w, h * 3), resampling_method)

                for variant in unprocessed_variants:
                    padded_img = apply_fixed_scale(crop_img, scale_factor, is_pixel_art, variant=variant)
                    out_filename = f"{num}{variant}{noteskin_suffix}.png"
                    padded_img.save(os.path.join(output_dir, out_filename))
                    processed_outputs.add((num, variant))
                    print(f"Saved: {out_filename}")

    print("Noteskin and splash conversion completed successfully.")

if __name__ == "__main__":
    process_noteskins()