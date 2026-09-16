import os
import json
import re

def parse_lenient_json(file_path):
    """Attempts standard json, then json5, then simple regex-based syntax fixes."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Standard JSON load
    try:
        return json.loads(content)
    except Exception:
        pass

    # 2. Try json5 if installed
    try:
        import json5
        return json5.loads(content)
    except Exception:
        pass

    # 3. Quick fallback fixes: missing commas between key-values, trailing commas
    # Add missing comma between string values and next keys
    fixed = re.sub(r'(["\d\]}])\s*\n\s*(["{])', r'\1,\n\2', content)
    # Remove trailing commas
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

    return json.loads(fixed)


def convert_psych_engine_charts():
    input_base_dir = "data"
    output_base_dir = "extracteddata"

    if not os.path.exists(input_base_dir):
        print(f"Directory '{input_base_dir}' does not exist.")
        return

    for song_folder in os.listdir(input_base_dir):
        song_path = os.path.join(input_base_dir, song_folder)
        
        if not os.path.isdir(song_path):
            continue

        all_jsons = [
            f for f in os.listdir(song_path) 
            if f.endswith('.json') 
            and 'metadata' not in f.lower() 
            and 'dialog' not in f.lower()
            and f.lower() != 'events.json'
        ]

        if not all_jsons:
            print(f"No valid chart JSON found in {song_folder}")
            continue

        target_json = None
        for j in all_jsons:
            if '-canon' in j.lower():
                target_json = j
                break

        if not target_json:
            for j in all_jsons:
                if '-hard' in j.lower():
                    target_json = j
                    break

        if not target_json:
            target_json = all_jsons[0]

        target_json_path = os.path.join(song_path, target_json)
        print(f"Processing: {target_json_path}")

        try:
            raw_data = parse_lenient_json(target_json_path)
        except Exception as e:
            print(f"Failed to read {target_json_path}: {e}")
            continue

        is_legacy = "song" in raw_data and isinstance(raw_data["song"], dict)
        data = raw_data["song"] if is_legacy else raw_data

        song_name = data.get("song", song_folder)
        bpm = data.get("bpm", 0)
        scroll_speed = data.get("speed", 1.0)
        p1 = data.get("player1", "bf")
        p2 = data.get("player2", "dad")
        gf = data.get("gfVersion", "gf")
        stage = data.get("stage", "stage")

        raw_noteskin = data.get("arrowSkin", "")
        if raw_noteskin:
            noteskin = raw_noteskin.replace("_note", "").replace("note_", "").replace("NOTE_assets", "").replace("note_assets", "")
            if not noteskin:
                noteskin = "default"
        else:
            noteskin = "default"

        # Base metadata format
        metadata_str = f"{{{song_name}}}: {{{bpm}}}: {{{scroll_speed}}}: {{{p1}}}: {{{p2}}}: {{{gf}}}: {{{stage}}}: {{{noteskin}}}"

        # Append player3 / player4 if present in chart
        p3 = data.get("player3")
        p4 = data.get("player4")
        
        if p3:
            metadata_str += f": {{{p3}}}"
        if p4:
            metadata_str += f": {{{p4}}}"

        initial_key_count = 4
        mania_val = data.get("mania", None)
        
        if mania_val is not None and str(mania_val).isdigit():
            initial_key_count = int(mania_val) + 1
        elif "keyCount" in data and str(data["keyCount"]).isdigit():
            initial_key_count = int(data["keyCount"])

        raw_events_list = data.get("events", [])
        
        standalone_events_path = os.path.join(song_path, "events.json")
        if os.path.exists(standalone_events_path):
            try:
                events_file_data = parse_lenient_json(standalone_events_path)
                ev_src = events_file_data.get("song", events_file_data) if isinstance(events_file_data, dict) else {}
                extra_events = ev_src.get("events", [])
                raw_events_list.extend(extra_events)
            except Exception as e:
                print(f"Failed to read extra events from {standalone_events_path}: {e}")

        parsed_events = []
        key_count_changes = []

        for event_group in raw_events_list:
            if len(event_group) >= 2:
                event_time = event_group[0] / 1000.0
                sub_events = event_group[1]
                for sub_event in sub_events:
                    if len(sub_event) >= 3:
                        e_name = sub_event[0]
                        e_val1 = sub_event[1]
                        e_val2 = sub_event[2]
                        
                        if e_name == "Set Key Count" and str(e_val1).isdigit():
                            key_count_changes.append((event_time, int(e_val1)))

                        formatted_str = f'{{{event_time}}}: {{"{e_name}"}}: {{"{e_val1}"}}: {{"{e_val2}"}}'
                        parsed_events.append((event_time, formatted_str))

        def get_key_count_at_time(note_time):
            current_kc = initial_key_count
            for kc_time, kc_val in key_count_changes:
                if note_time >= kc_time:
                    current_kc = kc_val
                else:
                    break
            return current_kc

        parsed_chart_entries = []
        notes_sections = data.get("notes", [])
        final_key_count = initial_key_count

        for section in notes_sections:
            must_hit = section.get("mustHitSection", False)
            section_notes = section.get("sectionNotes", [])
            is_first_note_in_section = True

            section_alt = section.get("altAnim", False) or section.get("altSection", False)
            section_gf = section.get("gfSection", False)

            fallback_custom_note = "Alt animation" if section_alt else ""

            for note in section_notes:
                if len(note) < 2:
                    continue

                time = note[0] / 1000.0
                raw_lane = note[1]
                hold_len = note[2] if len(note) > 2 else 0
                
                custom_note = note[3] if len(note) > 3 and note[3] else fallback_custom_note

                if raw_lane == -1 and isinstance(custom_note, str):
                    e_val2 = note[4] if len(note) > 4 else ""
                    formatted_str = f'{{{time}}}: {{"{custom_note}"}}: {{"{hold_len}"}}: {{"{e_val2}"}}'
                    parsed_events.append((time, formatted_str))
                    continue

                key_count = get_key_count_at_time(time)
                final_key_count = key_count

                is_opponent_note = False

                if is_legacy:
                    if must_hit:
                        if raw_lane < key_count:
                            note_id = raw_lane + key_count + 1
                        else:
                            note_id = (raw_lane - key_count) + 1
                            is_opponent_note = True
                    else:
                        if raw_lane < key_count:
                            note_id = raw_lane + 1
                            is_opponent_note = True
                        else:
                            note_id = raw_lane + 1
                else:
                    if 0 <= raw_lane < key_count:
                        note_id = raw_lane + key_count + 1
                    elif key_count <= raw_lane < key_count * 2:
                        note_id = (raw_lane - key_count) + 1
                        is_opponent_note = True
                    else:
                        note_id = raw_lane + 1

                if section_gf and is_opponent_note and not (len(note) > 3 and note[3]):
                    custom_note = "Gf sing"

                must_hit_flag = "1" if (is_first_note_in_section and must_hit) else ("0" if is_first_note_in_section else " ")
                is_first_note_in_section = False

                chart_entry = f"{{{time}}}: {{{note_id}}}: {{{custom_note}}}: {{{hold_len}}}: {{{must_hit_flag}}}"
                parsed_chart_entries.append((time, chart_entry))

        parsed_events.sort(key=lambda x: x[0])
        key_count_changes.sort(key=lambda x: x[0])
        events_str = " ".join([e[1] for e in parsed_events])

        parsed_chart_entries.sort(key=lambda x: x[0])
        chart_str = " ".join([e[1] for e in parsed_chart_entries])

        if final_key_count != 4:
            chart_str += f" @{final_key_count}"

        out_folder = os.path.join(output_base_dir, song_folder)
        os.makedirs(out_folder, exist_ok=True)

        with open(os.path.join(out_folder, "chart.txt"), "w", encoding="utf-8") as f:
            f.write(chart_str)

        with open(os.path.join(out_folder, "events.txt"), "w", encoding="utf-8") as f:
            f.write(events_str)

        with open(os.path.join(out_folder, "metadata.txt"), "w", encoding="utf-8") as f:
            f.write(metadata_str)

    print("Conversion completed successfully.")

if __name__ == "__main__":
    convert_psych_engine_charts()