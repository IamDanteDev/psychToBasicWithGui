import re
import os
import glob

POSITION_DIVISOR = 5

def fnf_to_scratch_x(fnf_x):
    return round((float(fnf_x) - 640.0) / POSITION_DIVISOR, 2)

def fnf_to_scratch_y(fnf_y):
    return round((360.0 - float(fnf_y)) / POSITION_DIVISOR - 175, 2)

def safe_convert(val, conversion_fn):
    # Converts numeric strings using the coordinate math; keeps raw text if non-numeric
    try:
        return str(conversion_fn(val))
    except (ValueError, TypeError):
        return val

def parse_lua_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    events = []
    
    # 1. Parse curStep blocks in onStepHit
    step_blocks = re.findall(r'if\s+curStep\s*==\s*(\d+)\s+then(.*?)end', content, re.DOTALL)
    for step_str, block in step_blocks:
        cur_step = int(step_str)
        
        for match in re.finditer(r"setProperty\s*\(\s*'([^']+)\.visible'\s*,\s*(true|false)\s*\)", block):
            obj = match.group(1)
            val = match.group(2)
            events.append((cur_step, "setproperty", obj, f"visible{val}"))

        for match in re.finditer(r"setObjectOrder\s*\(\s*'([^']+)'\s*,\s*([^,\)]+)", block):
            obj = match.group(1)
            val = match.group(2).strip()
            events.append((cur_step, "setobjectorder", obj, val))

        for match in re.finditer(r"setProperty\s*\(\s*'([^']+)\.y'\s*,\s*([^,\)]+)\s*\)", block):
            obj = match.group(1)
            val = safe_convert(match.group(2).strip(), fnf_to_scratch_y)
            events.append((cur_step, "sety", obj, val))

        for match in re.finditer(r"setProperty\s*\(\s*'([^']+)\.x'\s*,\s*([^,\)]+)\s*\)", block):
            obj = match.group(1)
            val = safe_convert(match.group(2).strip(), fnf_to_scratch_x)
            events.append((cur_step, "setx", obj, val))

    # 2. Parse general statements outside/inside onCreate
    for match in re.finditer(r"setProperty\s*\(\s*'([^']+)\.visible'\s*,\s*(true|false)\s*\)", content):
        obj, val = match.groups()
        if not any(e[2] == obj and e[1] == "setproperty" for e in events):
            events.append((0, "setproperty", obj, f"visible{val}"))

    for match in re.finditer(r"setObjectOrder\s*\(\s*'([^']+)'\s*,\s*([^,\)]+)", content):
        obj, val = match.group(1), match.group(2).strip()
        if not any(e[2] == obj and e[1] == "setobjectorder" for e in events):
            events.append((0, "setobjectorder", obj, val))

    for match in re.finditer(r"setProperty\s*\(\s*'([^']+)\.y'\s*,\s*([^,\)]+)\s*\)", content):
        obj = match.group(1)
        val = safe_convert(match.group(2).strip(), fnf_to_scratch_y)
        if not any(e[2] == obj and e[1] == "sety" for e in events):
            events.append((0, "sety", obj, val))

    for match in re.finditer(r"setProperty\s*\(\s*'([^']+)\.x'\s*,\s*([^,\)]+)\s*\)", content):
        obj = match.group(1)
        val = safe_convert(match.group(2).strip(), fnf_to_scratch_x)
        if not any(e[2] == obj and e[1] == "setx" for e in events):
            events.append((0, "setx", obj, val))

    events.sort(key=lambda x: x[0])
    return events

def main():
    lua_files = glob.glob("*.lua")
    all_formatted_events = []

    for file in lua_files:
        parsed_events = parse_lua_file(file)
        for step, ev_name, val1, val2 in parsed_events:
            formatted = f'{{{step}}}: {{"{ev_name}"}}: {{"{val1}"}}: {{"{val2}"}}'
            all_formatted_events.append(formatted)

    output_string = " ".join(all_formatted_events)

    with open("converted_events.txt", "w", encoding="utf-8") as f:
        f.write(output_string)

    print(f"Successfully converted {len(lua_files)} file(s) into converted_events.txt")

if __name__ == "__main__":
    main()