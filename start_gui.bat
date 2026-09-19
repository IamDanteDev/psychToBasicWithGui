@echo off
rem spanish - que aburrido escribir pero solamente abre la gui pero este es solo para windows
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo.
    echo [PsychtoBasic] Creating local environment...
    py -3 -m venv venv 2>nul
    if errorlevel 1 python -m venv venv
    if errorlevel 1 (
        echo [PsychtoBasic] ERROR: Python not found or venv failed. Install Python 3 first.
        pause
        exit /b 1
    )
    echo [PsychtoBasic] Installing dependencies (one time only)...
    "venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
    if errorlevel 1 (
        echo [PsychtoBasic] ERROR: dependency install failed.
        pause
        exit /b 1
    )
)

echo [PsychtoBasic] Starting GUI (open gui)
"venv\Scripts\python.exe" gui.py
if errorlevel 1 pause
endlocal
