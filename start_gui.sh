#!/usr/bin/env bash
# SPANISH - este es el archivo que se abre desde la terminal para usar la gui en macOS o linux pero solo lo testee en linux porque macOS no me gusta y tampoco tengo algo que lo use XD
set -e
cd "$(dirname "$0")"

if [ ! -x "venv/bin/python" ]; then
    echo "[PortToBasic] Creating local environment..."
    python3 -m venv venv
    echo "[PortToBasic] Installing dependencies (one time only)..."
    venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
fi

echo "[PortToBasic] Starting GUI (open gui)"
exec venv/bin/python gui.py
