import os
import shutil
import xml.etree.ElementTree as ET
from PIL import Image
from pydub import AudioSegment

def process_replace_assets():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_base_dir = os.path.join(script_dir, "extractedreplace")
    
    asset_mappings = {
        "sounds/scrollMenu.ogg": ["Menu//Menu", "Menu//Text"],
        "sounds/confirmMenu.ogg": ["Menu//Menu", "Menu//Text", "Menu//IntroMenu"],
        "sounds/cancelMenu.ogg": ["Menu//Menu", "Menu//Text"],
        "music/breakfast.ogg": ["Menu//Text"],
        "music/freakyMenu.ogg": ["Menu//IntroMenu"],
        
        ("sounds/intro3.ogg", "sounds/default/intro3.ogg"): ["UI//Countdown"],
        ("sounds/intro2.ogg", "sounds/default/intro2.ogg"): ["UI//Countdown"],
        ("sounds/intro1.ogg", "sounds/default/intro1.ogg"): ["UI//Countdown"],
        ("sounds/introGo.ogg", "sounds/default/introGo.ogg"): ["UI//Countdown"],

        ("music/gameOver.ogg", "music/deaths/bf-dead/loop.ogg"): ["Game//Death"],
        ("music/gameOverEnd.ogg", "music/deaths/bf-dead/retry.ogg"): ["Game//Death"],
        
        ("images/ready2.png", "images/ready.png"): ["UI//Countdown"],
        ("images/set2.png", "images/set.png"): ["UI//Countdown"],
        ("images/go2.png", "images/go.png"): ["UI//Countdown"],

        ("images/UI/game/healthbar.png", "images/healthbar.png"): ["UI//Health/icons"],

        "images/menuBG.png": ["Menu//Menu"],
        "images/sick.png": ["UI//Judgments"],
        "images/good.png": ["UI//Judgments"],
        "images/bad.png": ["UI//Judgments"],
        "images/shit.png": ["UI//Judgments"],

        "assets/SFX/Select.mp3": ["Menu//Menu", "Menu//Text", "Menu//IntroMenu"],
        "assets/SFX/Error.mp3":  ["Menu//Menu", "Menu//Text"],
    }

    for i in range(10):
        asset_mappings[f"images/num{i}.png"] = ["UI//Judgments"]

    os.makedirs(output_base_dir, exist_ok=True)

    for key_path, target_locations in asset_mappings.items():
        candidate_paths = [key_path] if isinstance(key_path, str) else key_path
        src_path = None
        chosen_rel_path = candidate_paths[0]

        for rel_path in candidate_paths:
            possible_path = os.path.join(script_dir, rel_path)
            if os.path.exists(possible_path):
                src_path = possible_path
                chosen_rel_path = rel_path
                break

        if not src_path:
            print(f"Skipping missing asset: {candidate_paths[0]}")
            continue

        filename = os.path.basename(chosen_rel_path)
        base_name, ext = os.path.splitext(filename)
        
        if base_name in ["ready2", "set2", "go2"]:
            base_name = base_name.replace("2", "")

        if filename in ["gameOver.ogg", "loop.ogg"]:
            out_filename = "gameOver.mp3"
            txt_filename = "gameOver.txt"
        elif filename in ["gameOverEnd.ogg", "retry.ogg"]:
            out_filename = "gameOverEnd.mp3"
            txt_filename = "gameOverEnd.txt"
        if filename == "shit.png":
            out_filename = "shoot.png"
            txt_filename = "shoot.txt"
        elif filename == "Select.mp3":
            out_filename = "confirmMenu.mp3"
            txt_filename = "confirmMenu.txt"
        elif filename == "Error.mp3":
            out_filename = "cancelMenu.mp3"
            txt_filename = "cancelMenu.txt"
        else:
            out_filename = f"{base_name}.mp3" if ext.lower() == ".ogg" else f"{base_name}{ext}"
            txt_filename = f"{base_name}.txt"

        dest_asset_path = os.path.join(output_base_dir, out_filename)

        if ext.lower() == ".ogg":
            try:
                audio = AudioSegment.from_ogg(src_path)
                audio.export(dest_asset_path, format="mp3", bitrate="64k")
                print(f"Converted & Compressed: {chosen_rel_path} -> {out_filename}")
            except Exception as e:
                print(f"Failed to convert {chosen_rel_path}: {e}")
                continue
        else:
            should_scale_2_5x = (
                base_name in ["sick", "good", "bad", "shit", "shoot"] or 
                (base_name.startswith("num") and base_name[3:].isdigit())
            )

            if should_scale_2_5x:
                with Image.open(src_path) as img:
                    new_w = max(1, int(img.width * 2.5))
                    new_h = max(1, int(img.height * 2.5))
                    scaled_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    scaled_img.save(dest_asset_path, optimize=True, compress_level=9)
                print(f"Scaled (2.5x Optimized) & Saved: {chosen_rel_path} -> {out_filename}")
            else:
                shutil.copy2(src_path, dest_asset_path)
                print(f"Copied unscaled original image: {chosen_rel_path} -> {out_filename}")

        dest_txt_path = os.path.join(output_base_dir, txt_filename)
        txt_content = "\n".join(target_locations)
        
        with open(dest_txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)
        
        print(f"Created location TXT: {txt_filename}")

    logo_png_path = os.path.join(script_dir, "images", "logoBumpin.png")
    logo_xml_path = os.path.join(script_dir, "images", "logoBumpin.xml")

    if os.path.exists(logo_png_path) and os.path.exists(logo_xml_path):
        try:
            tree = ET.parse(logo_xml_path)
            root = tree.getroot()
            first_subtexture = root.find("SubTexture")

            if first_subtexture is not None:
                x = int(first_subtexture.attrib.get("x", 0))
                y = int(first_subtexture.attrib.get("y", 0))
                w = int(first_subtexture.attrib.get("width", 0))
                h = int(first_subtexture.attrib.get("height", 0))

                if w > 0 and h > 0:
                    with Image.open(logo_png_path) as img:
                        first_frame = img.crop((x, y, x + w, y + h))
                        dest_logo_path = os.path.join(output_base_dir, "logoBumpin.png")
                        first_frame.save(dest_logo_path, optimize=True, compress_level=9)

                    dest_logo_txt = os.path.join(output_base_dir, "logoBumpin.txt")
                    with open(dest_logo_txt, "w", encoding="utf-8") as f:
                        f.write("Menu//IntroMenu")

                    print("Extracted original first frame of logoBumpin.png -> Menu//IntroMenu")
        except Exception as e:
            print(f"Failed to process logoBumpin.png frame: {e}")
    else:
        print("Skipping logoBumpin: PNG or XML spritesheet missing.")

    print("Asset replacement processing completed.")

if __name__ == "__main__":
    process_replace_assets()