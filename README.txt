Psych to Basic - FNF (Psych Engine) mod to Scratch porting tool with GUI
=====================================================================

Converts Friday Night Funkin' mods (Psych Engine format) into a playable
Scratch project (.sb3).

EASY START (GUI)
----------------
- Windows: double-click start_gui.bat
- macOS / Linux: run ./start_gui.sh

The launcher creates a local virtual environment on first run, installs the
dependencies, and starts the GUI. Nothing is installed globally.

USAGE (GUI)
----------
1. Click "Select Mod Folder" and pick the root of the mod (marked by
   pack.png for Psych Engine mods, or _polymod_meta.json for v-slice /
   vanilla FNF 0.8 mods). The tool auto-copies the missing scripts and the
   blank engine into the mod folder, then runs each conversion step in
   order.
2. Choose the base engine in the "Base engine (.sb3)" dropdown — this selects
   which Scratch template the build step starts from. Drop extra .sb3 files
   next to this app and they appear in the dropdown.
3. Press Run. The final .sb3 is written next to the blank template as
   built_<template>.sb3 inside the mod folder.
4. Open the generated .sb3 in Scratch or Turbowarp to play.

MANUAL / CLI USE
----------------
1. Copy the files from this folder into the root of the mod
   (marked by pack.png or _polymod_meta.json).
2. Install Python and dependencies:
     pip install audioop-lts Pillow pydub mutagen customtkinter
   (On Windows, install Python 3.13 from the Microsoft Store.)
3. Install FFmpeg:
     winget install Gyan.FFmpeg
4. Run:
     python port.py

REQUIREMENTS
------------
- Python 3.10+ (3.13 recommended on Windows)
- FFmpeg on PATH (used for OGG -> MP3 conversion)
- No global installs needed when using start_gui.sh / start_gui.bat
