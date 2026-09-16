import os
from pydub import AudioSegment

def process_songs():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_dir, "songs")
    output_dir = os.path.join(base_dir, "extractedsongs")

    if not os.path.exists(input_dir):
        print(f"Directory '{input_dir}' does not exist.")
        return

    os.makedirs(output_dir, exist_ok=True)

    song_folders = [f for f in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, f))]
    total_songs = len(song_folders)

    if total_songs == 0:
        print("No song folders found.")
        return

    # Automatically set to compress at 64k
    bitrate = "64k"

    print(f"\nStarting song processing... Found {total_songs} song folder(s).\n")

    for song_idx, song_folder in enumerate(song_folders, start=1):
        song_path = os.path.join(input_dir, song_folder)
        target_folder = os.path.join(output_dir, song_folder)
        os.makedirs(target_folder, exist_ok=True)

        print(f"[{song_idx}/{total_songs}] Processing song: '{song_folder}'")

        files = os.listdir(song_path)
        song_folder_lower = song_folder.lower()

        ogg_files = [f for f in files if f.endswith(".ogg")]
        total_ogg = len(ogg_files)

        # Detect files containing -opponent or -player (case-insensitive)
        voice_files = [
            f for f in ogg_files 
            if "-opponent" in f.lower() or "-player" in f.lower()
        ]

        # Merge matching split voice files into single Voices file
        if voice_files:
            out_name = f"Voices_{song_folder_lower}.mp3"
            out_file_path = os.path.join(target_folder, out_name)

            if os.path.exists(out_file_path):
                print(f"  [{song_idx}/{total_songs}] Skipping merged '{out_name}' (already exists)")
            else:
                print(f"  [{song_idx}/{total_songs}] Merging voice files: {', '.join(voice_files)}...")
                merged_audio = None

                for vf in voice_files:
                    vf_path = os.path.join(song_path, vf)
                    audio_track = AudioSegment.from_file(vf_path)
                    
                    if merged_audio is None:
                        merged_audio = audio_track
                    else:
                        merged_audio = merged_audio.overlay(audio_track)

                print(f"  [{song_idx}/{total_songs}] Exporting merged '{out_name}' at {bitrate}...")
                merged_audio.export(out_file_path, format="mp3", bitrate=bitrate)
                print(f"  [{song_idx}/{total_songs}] Finished merged '{out_name}'")

        # Process individual remaining .ogg files
        for file_idx, file in enumerate(ogg_files, start=1):
            if file in voice_files:
                print(f"  [{song_idx}/{total_songs}] (File {file_idx}/{total_ogg}) Skipping '{file}' (merged into Voices)")
                continue

            name_without_ext = os.path.splitext(file)[0]
            
            if name_without_ext.lower() == "inst":
                base_name = f"Inst_{song_folder_lower}"
            elif name_without_ext.lower() == "voices":
                base_name = f"Voices_{song_folder_lower}"
            else:
                base_name = f"{name_without_ext.capitalize()}_{song_folder_lower}"

            out_name = f"{base_name}.mp3"
            out_file_path = os.path.join(target_folder, out_name)
            file_path = os.path.join(song_path, file)

            if os.path.exists(out_file_path):
                print(f"  [{song_idx}/{total_songs}] (File {file_idx}/{total_ogg}) Skipping '{out_name}' (already exists)")
                continue

            print(f"  [{song_idx}/{total_songs}] (File {file_idx}/{total_ogg}) Reading '{file}'...")
            audio = AudioSegment.from_file(file_path)
            print(f"  [{song_idx}/{total_songs}] (File {file_idx}/{total_ogg}) Exporting '{out_name}' at {bitrate}...")
            audio.export(out_file_path, format="mp3", bitrate=bitrate)

            print(f"  [{song_idx}/{total_songs}] (File {file_idx}/{total_ogg}) Finished '{out_name}'")

        print(f"[{song_idx}/{total_songs}] Finished song folder: '{song_folder}'\n")

    print(f"All {total_songs} song(s) processed successfully!")

if __name__ == "__main__":
    process_songs()