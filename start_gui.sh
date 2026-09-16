#!/usr/bin/env bash
# Psychto Basic - GUI launcher (macOS / Linux)
# Creates a local virtual environment inside the project on first run,
# installs the dependencies there, then starts the GUI. Nothing global.
set -e
cd "$(dirname "$0")"

if [ ! -x "venv/bin/python" ]; then
    echo "[PsychtoBasic] Creating local environment..."
    python3 -m venv venv
    echo "[PsychtoBasic] Installing dependencies (one time only)..."
    venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
fi

echo "[PsychtoBasic] Starting GUI..."
exec venv/bin/python gui.py