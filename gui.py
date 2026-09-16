"""Psychto Basic - Mod Port GUI (modern customtkinter build)

Graphical wrapper around the FNF (Psych Engine) mod -> Scratch (.sb3) port pipeline.
Runs the same scripts as port.py but step by step, with a live colorized log,
progress tracking, and cancel support.
"""

import glob
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

# Same order as port.py
PREREQUISITE_SCRIPTS = [
    "weeks.py",
    "characters.py",
    "icons.py",
    "notes.py",
    "noteskins.py",
    "replace.py",
    "songs.py",
    "songsdata.py",
    "stages.py",
]

APP_TITLE = "Psych To Basic"
APP_SUBTITLE = "FNF mod  →  Scratch .sb3 port"
DEFAULT_FOLDER = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(DEFAULT_FOLDER, "assets")
GENERATED_DIR = os.path.join(DEFAULT_FOLDER, "generated")
CONFIG_PATH = os.path.join(GENERATED_DIR, "psychtobasic_config.json")

# Logo banner (replaces the text title when all files exist)
LOGO_FILES = [
    ("PsychEngineLogo.png", 46),
    ("FunkinArrowRight.png", 40),
    ("BasicEngineLogo.png", 46),
]

ACCENT = "#3a8df0"
GREEN = "#2fa572"
RED = "#e05252"
YELLOW = "#e0b84c"
GRAY = "#8a8a8a"

# --- UI strings (EN / ES). Pipeline log lines stay English (they mirror console). ---
STRINGS = {
    "en": {
        "app_title": "Psych To Basic",
        "app_subtitle": "FNF mod  →  Scratch .sb3 port",
        "app_log_title": "Psych To Basic — Log",
        "status_ready": "Ready",
        "status_running": "Running",
        "status_failed": "Failed",
        "status_error": "Error",
        "status_cancelled": "Cancelled",
        "status_cancelling": "Cancelling...",
        "status_done": "Done",
        "pipeline_cancelled": "--- Pipeline cancelled by user ---",
        "step_failed": "!!! STEP FAILED: '{step}' (exit code {code})",
        "finish_success": "Pipeline finished successfully.",
        "finish_failed_step": "Step '{step}' failed (exit code {code}).",
        "internal_error": "Internal error: {exc}",
        "folder_label": "Mod folder",
        "browse": "Browse...",
        "check_mod": "Check mod",
        "folder_hint": "Mod root folder (pack.png). Missing toolkit files are auto-staged on Run.",
        "steps_label": "Steps to run",
        "check_all": "Check all",
        "uncheck_all": "Uncheck all",
        "log_label": "Log",
        "save_log": "Save log",
        "open_folder": "Open folder",
        "open_turbowarp": "Open in TurboWarp",
        "cancel": "Cancel",
        "cancel_x": "✖ Cancel",
        "ffmpeg_missing": "⚠ FFmpeg missing",
        "run": "▶  Run",
        "assets_preview": "Assets",
        "err_title": "Error",
        "done_title": "Done",
        "folder_not_exist": "Folder does not exist:\n{folder}",
        "no_steps_title": "No steps",
        "no_steps_body": "Select at least one step to run.",
        "no_sb3_title": "No .sb3 found",
        "no_sb3_body": "No .sb3 project was found in the selected folder.\n"
                       "The build step will produce no output.\n\nContinue anyway?",
        "save_log_title": "Save log",
        "save_log_empty": "Nothing in the log yet.",
        "turbowarp_title": "Open in TurboWarp",
        "turbowarp_no_build": "Build the project first — no built_*.sb3 found.",
        "turbowarp_server_fail": "Could not start the local file server.",
        "ffmpeg_title": "FFmpeg required",
        "ffmpeg_body": "FFmpeg is used to convert OGG audio to MP3 during the port.\n\n"
                       "Install it, then close and reopen this app:\n\n    {cmd}",
        "ffmpeg_warn_log": "FFmpeg or ffprobe not found — OGG→MP3 conversion will fail. "
                           "Click the '{btn}' button for install instructions.",
        "no_prereq_warn": "No prerequisite scripts yet — they will be auto-staged from the tool folder on Run.",
        "staged_log": "Staged {n} toolkit file(s) into mod folder: {names}",
        "build_step": "Building Scratch project (.sb3)",
        "run_step": "Running {step}",
        "auto_tag": "(auto)",
        "ck_pack": "pack.png",
        "ck_chars": "data/characters JSONs",
        "ck_songs": "data/songs JSONs",
        "ck_weeks": "data/weeks JSONs",
        "ck_toolkit": "toolkit scripts",
        "ck_sb3": "Scratch template (.sb3)",
        "ck_audio": "audio files (ogg/mp3)",
        "ck_icons": "character icons (png)",
        "ck_ffmpeg": "ffmpeg on PATH",
        "ck_missing": "missing: {list}",
        "ck_present": "all present",
        "ck_found": "{n} found",
        "mod_check_header": "Mod check: {folder}",
        "mod_check_done": "Mod check finished.",
        "preview_title": "Asset preview",
        "preview_none": "No images found in the mod folder.",
        "check_mod_title": "Check mod",
        "rdy_title": "Port readiness",
        "rdy_no_mod": "Not a mod folder",
        "rdy_root": "Mod root",
        "rdy_weeks": "Weeks",
        "rdy_chars": "Characters",
        "rdy_charts": "Charts",
        "rdy_audio": "Audio",
        "rdy_stages": "Stages",
        "rdy_icons": "Icons",
        "rdy_notes": "Note types",
        "rdy_noteskins": "Noteskins",
        "rdy_template": ".sb3 template",
        "rdy_ffmpeg": "FFmpeg",
        "rdy_auto": "auto-detected: {name}",
        "rdy_verdict_yes": "Porteable: YES — all core pieces present",
        "rdy_verdict_no": "Porteable: NO — missing {missing}",
        "rdy_verdict_partial": "Porteable: PARTIAL — missing {missing}",
    },
    "es": {
        "app_title": "Psych To Basic",
        "app_subtitle": "Mod FNF  →  Puerto a Scratch .sb3",
        "app_log_title": "Psych To Basic — Registro",
        "status_ready": "Listo",
        "status_running": "Corriendo",
        "status_failed": "Error",
        "status_error": "Error",
        "status_cancelled": "Cancelado",
        "status_cancelling": "Cancelando...",
        "status_done": "Listo",
        "pipeline_cancelled": "--- Pipeline cancelado por el usuario ---",
        "step_failed": "!!! PASO FALLÓ: '{step}' (código {code})",
        "finish_success": "Pipeline finalizado correctamente.",
        "finish_failed_step": "El paso '{step}' falló (código {code}).",
        "internal_error": "Error interno: {exc}",
        "folder_label": "Carpeta del mod",
        "browse": "Examinar...",
        "check_mod": "Comprobar mod",
        "folder_hint": "Carpeta raíz del mod (pack.png). Los archivos del toolkit faltantes se copian solos al ejecutar.",
        "steps_label": "Pasos a ejecutar",
        "check_all": "Marcar todos",
        "uncheck_all": "Desmarcar todos",
        "log_label": "Registro",
        "save_log": "Guardar registro",
        "open_folder": "Abrir carpeta",
        "open_turbowarp": "Abrir en TurboWarp",
        "cancel": "Cancelar",
        "cancel_x": "✖ Cancelar",
        "ffmpeg_missing": "⚠ Falta FFmpeg",
        "run": "▶  Ejecutar",
        "assets_preview": "Recursos",
        "err_title": "Error",
        "done_title": "Listo",
        "folder_not_exist": "La carpeta no existe:\n{folder}",
        "no_steps_title": "Sin pasos",
        "no_steps_body": "Selecciona al menos un paso para ejecutar.",
        "no_sb3_title": "No se encontró .sb3",
        "no_sb3_body": "No se encontró ningún proyecto .sb3 en la carpeta seleccionada.\n"
                       "El paso de construcción no producirá salida.\n\n¿Continuar de todos modos?",
        "save_log_title": "Guardar registro",
        "save_log_empty": "El registro está vacío.",
        "turbowarp_title": "Abrir en TurboWarp",
        "turbowarp_no_build": "Primero construye el proyecto — no se encontró built_*.sb3.",
        "turbowarp_server_fail": "No se pudo iniciar el servidor local.",
        "ffmpeg_title": "Se requiere FFmpeg",
        "ffmpeg_body": "FFmpeg se usa para convertir audio OGG a MP3 durante el port.\n\n"
                       "Instálalo y luego cierra y reabre la app:\n\n    {cmd}",
        "ffmpeg_warn_log": "No se encontró FFmpeg o ffprobe — la conversión OGG→MP3 fallará. "
                           "Haz clic en el botón '{btn}' para ver las instrucciones.",
        "no_prereq_warn": "Aún no hay scripts del toolkit — se copiarán solos desde la carpeta de la herramienta al ejecutar.",
        "staged_log": "Se copiaron {n} archivo(s) del toolkit a la carpeta del mod: {names}",
        "build_step": "Construyendo proyecto Scratch (.sb3)",
        "run_step": "Ejecutando {step}",
        "auto_tag": "(auto)",
        "ck_pack": "pack.png",
        "ck_chars": "JSONs de data/characters",
        "ck_songs": "JSONs de data/songs",
        "ck_weeks": "JSONs de data/weeks",
        "ck_toolkit": "scripts del toolkit",
        "ck_sb3": "Plantilla Scratch (.sb3)",
        "ck_audio": "archivos de audio (ogg/mp3)",
        "ck_icons": "iconos de personajes (png)",
        "ck_ffmpeg": "ffmpeg en PATH",
        "ck_missing": "faltan: {list}",
        "ck_present": "todo presente",
        "ck_found": "{n} encontrados",
        "mod_check_header": "Comprobación del mod: {folder}",
        "mod_check_done": "Comprobación del mod finalizada.",
        "preview_title": "Vista previa de recursos",
        "preview_none": "No se encontraron imágenes en la carpeta del mod.",
        "check_mod_title": "Comprobar mod",
        "rdy_title": "Preparación del port",
        "rdy_no_mod": "No es una carpeta de mod",
        "rdy_root": "Raíz del mod",
        "rdy_weeks": "Semanas",
        "rdy_chars": "Personajes",
        "rdy_charts": "Canciones (charts)",
        "rdy_audio": "Audio",
        "rdy_stages": "Escenarios",
        "rdy_icons": "Iconos",
        "rdy_notes": "Note types",
        "rdy_noteskins": "Noteskins",
        "rdy_template": "Plantilla .sb3",
        "rdy_ffmpeg": "FFmpeg",
        "rdy_auto": "auto-detectado: {name}",
        "rdy_verdict_yes": "Porteable: SÍ — todos los componentes clave presentes",
        "rdy_verdict_no": "Porteable: NO — falta {missing}",
        "rdy_verdict_partial": "Porteable: PARCIAL — falta {missing}",
    },
}


def _safe_glob(dirpath, tail="*", recursive=False):
    """glob.glob with the directory part escaped so '[' in folder names works.
    Folder names like 'PLAYTIME [2026]' would otherwise be parsed as glob
    character classes and match nothing."""
    if not os.path.isdir(dirpath):
        return []
    prefix = glob.escape(dirpath.rstrip(os.sep))
    if recursive:
        pattern = os.path.join(prefix, "**", "*")
    else:
        pattern = os.path.join(prefix, tail)
    return glob.glob(pattern, recursive=recursive)


class _CORSHandler(SimpleHTTPRequestHandler):
    """Local file server with CORS so TurboWarp (https) can fetch the .sb3."""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, *args):
        pass


class PortGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("940x680")
        self.minsize(620, 480)
        self._set_app_icon()

        self._init_vars()

        self.worker = None
        self.proc = None
        self.cancel_requested = False
        self.log_queue = queue.Queue()
        self.log_buffer = []
        self._readiness_job = None

        self._ffmpeg_ok = self._check_ffmpeg()

        self._build_ui()
        self._build_overlay()
        self._load_bf_frames()
        self._refresh_steps()

        self.after(100, self._drain_queue)
        self.mod_folder.trace_add("write", self._schedule_readiness)
        if not self._ffmpeg_ok:
            self.log(
                self._tr("ffmpeg_warn_log", btn=self._tr("ffmpeg_missing")),
                "warn",
            )
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._stop_music()
        if self._http_server is not None:
            threading.Thread(
                target=self._http_server.shutdown, daemon=True
            ).start()
        self.destroy()

    # ---------- Config & environment ----------

    def _tr(self, key, **fmt):
        table = STRINGS.get(self.lang, STRINGS["en"])
        text = table.get(key, STRINGS["en"].get(key, key))
        if fmt:
            try:
                return text.format(**fmt)
            except (KeyError, IndexError):
                return text
        return text

    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save_config(self, folder):
        try:
            os.makedirs(GENERATED_DIR, exist_ok=True)
            data = {"last_mod_folder": folder}
            if getattr(self, "lang", "en"):
                data["lang"] = self.lang
            with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            self.log(f"Config save failed: {exc}", "warn")

    def _check_ffmpeg(self):
        """pydub needs both ffmpeg and ffprobe on PATH for OGG -> MP3."""
        return (
            shutil.which("ffmpeg") is not None
            and shutil.which("ffprobe") is not None
        )

    def _show_ffmpeg_help(self):
        if sys.platform.startswith("win"):
            cmd = "winget install Gyan.FFmpeg"
        elif sys.platform == "darwin":
            cmd = "brew install ffmpeg"
        else:
            cmd = "sudo apt install ffmpeg"
        messagebox.showinfo(
            self._tr("ffmpeg_title"),
            self._tr("ffmpeg_body", cmd=cmd),
        )

    def _set_lang(self, lang):
        if lang == self.lang or self.pipeline_running:
            return
        self.lang = lang
        self._save_config(self.mod_folder.get().strip() or DEFAULT_FOLDER)
        self._rebuild_ui()

    def _rebuild_ui(self):
        """Rebuild all UI widgets with the current language."""
        if getattr(self, "_ui_outer", None) is not None:
            self._ui_outer.destroy()
        self._build_ui()
        self._build_overlay()
        self._refresh_steps()
        self.progress.set(self.progress_display)
        self._set_running(False)   # refresh button states after rebuild
        self._update_readiness()
        target = self.main_log_text
        target.configure(state="normal")
        for line, kind in self.log_buffer:
            target.insert("end", line + "\n", kind)
        target.see("end")
        target.configure(state="disabled")

    def _preview_assets(self):
        """Show pack.png + character icons from the mod folder in a grid."""
        folder = self.mod_folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror(
                self._tr("check_mod_title"),
                self._tr("folder_not_exist", folder=folder),
            )
            return

        paths = []
        pack = os.path.join(folder, "pack.png")
        if os.path.exists(pack):
            paths.append(pack)
        chars = os.path.join(folder, "data", "characters")
        if os.path.isdir(chars):
            paths.extend(
                sorted(_safe_glob(chars, "*.png", recursive=True))
            )
        # Legacy layout (charts flat in a root icons/ folder)
        legacy = os.path.join(folder, "icons")
        if os.path.isdir(legacy):
            paths.extend(sorted(_safe_glob(legacy, "*.png")))
        paths = paths[:200]

        win = ctk.CTkToplevel(self)
        win.title(self._tr("preview_title"))
        win.geometry("760x520")
        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        if not paths:
            ctk.CTkLabel(
                scroll, text=self._tr("preview_none"), text_color=GRAY
            ).pack(pady=20)
            return

        shown = 0
        for i, path in enumerate(paths):
            try:
                im = Image.open(path)
                im.thumbnail((96, 96))
                photo = ImageTk.PhotoImage(im)
            except Exception:
                continue
            card = ctk.CTkFrame(scroll, corner_radius=8)
            card.grid(row=shown // 6, column=shown % 6, padx=6, pady=6)
            img_label = ctk.CTkLabel(card, image=photo, text="")
            img_label.image = photo  # keep a reference alive
            img_label.pack(padx=6, pady=(6, 0))
            ctk.CTkLabel(
                card,
                text=os.path.basename(path),
                font=ctk.CTkFont(size=10),
                text_color=GRAY,
            ).pack(padx=6, pady=(0, 6))
            shown += 1

    # ---------- App icon ----------

    def _set_app_icon(self):
        """Set the taskbar / window-bar icon from assets/AppIcon.png.

        Windows only: it honors _NET_WM_ICON (set by iconphoto) with no
        external files. On Linux we do NOT touch any system files, so no
        .desktop entry is created and the window keeps the system default
        icon.
        """
        if not sys.platform.startswith("win"):
            return
        from PIL import ImageTk
        icon_path = os.path.join(ASSETS_DIR, "AppIcon.png")
        try:
            img = Image.open(icon_path)
            self._icon_photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon_photo)
        except Exception as exc:
            print(f"App icon load failed: {exc!r}")

    # ---------- Music (plays while porting) ----------

    def _play_music(self):
        self._stop_music()
        files = sorted(
            f
            for f in _safe_glob(os.path.join(ASSETS_DIR, "Music"), "*")
            if f.lower().endswith((".mp3", ".ogg", ".wav", ".flac", ".m4a"))
        )
        if not files:
            self.log("Music: no audio files in assets/Music — skipping soundtrack.", "dim")
            return
        cmd = None
        if shutil.which("mpv"):
            cmd = ["mpv", "--no-video", "--loop-playlist=inf", "--volume=60", "--really-quiet", *files]
        elif shutil.which("ffplay"):
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loop", "0", files[0]]
        elif shutil.which("play"):
            cmd = ["play", "-q", files[0], "repeat", "999999"]
        elif shutil.which("aplay") and files[0].lower().endswith(".wav"):
            cmd = ["aplay", "-q", files[0]]
        if not cmd:
            self.log("Music: no player found (mpv/ffplay/play/aplay).", "warn")
            return
        try:
            self.music_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self.log(f"Music: could not start player: {exc}", "warn")
            self.music_proc = None
            return
        extra = f" +{len(files) - 1} more" if len(files) > 1 else ""
        self.log(f"Music: playing {os.path.basename(files[0])}{extra}", "step")

    def _stop_music(self):
        if self.music_proc and self.music_proc.poll() is None:
            self.music_proc.terminate()
            try:
                self.music_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.music_proc.kill()
        self.music_proc = None

    def _init_vars(self):
        os.makedirs(GENERATED_DIR, exist_ok=True)
        cfg = self._load_config()
        self.lang = cfg.get("lang", "en")
        saved = cfg.get("last_mod_folder", "")
        if saved and not os.path.isdir(saved):
            saved = ""
        self.mod_folder = ctk.StringVar(
            value=saved if saved else DEFAULT_FOLDER
        )
        self.step_vars = {}
        self.status_var = ctk.StringVar(value=self._tr("status_ready"))
        self.progress_var = ctk.DoubleVar(value=0.0)
        # BF loading animation state (initialized before overlay build)
        self.bf_display_w = 110
        self.bf_display_h = 116
        self.bf_frames = []
        self.bf_frame_idx = 0
        self.bf_anim_job = None
        # Smooth progress state
        self.progress_display = 0.0
        self.progress_target = 0.0
        self._step_end = None
        self.tween_job = None
        self.pipeline_running = False
        self.music_proc = None
        self._http_server = None
        self._server_dir = None
        self._http_port = 0

    # ---------- UI ----------

    def _build_header_logos(self, header):
        """Show PsychEngine + arrow + BasicEngine logos; fall back to text title."""
        try:
            imgs = []
            for filename, target_h in LOGO_FILES:
                path = os.path.join(ASSETS_DIR, filename)
                if not os.path.exists(path):
                    raise FileNotFoundError(path)
                im = Image.open(path)
                w, h = im.size
                display_w = max(1, int(target_h * (w / h)))
                imgs.append(
                    ctk.CTkImage(
                        light_image=im,
                        dark_image=im,
                        size=(display_w, target_h),
                    )
                )

            logo_row = ctk.CTkFrame(header, fg_color="transparent")
            logo_row.pack(side="left", padx=18, pady=10)
            for img in imgs:
                ctk.CTkLabel(logo_row, image=img, text="").pack(
                    side="left", padx=(0, 12)
                )
            return
        except Exception as exc:
            print(f"LOGO FALLBACK: {exc!r}")

        # Fallback: plain text title
        ctk.CTkLabel(
            header,
            text=self._tr("app_title"),
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left", padx=(18, 0), pady=14)
        ctk.CTkLabel(
            header,
            text=self._tr("app_subtitle"),
            font=ctk.CTkFont(size=13),
            text_color=GRAY,
        ).pack(side="left", padx=(12, 0), pady=14)

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=18, pady=(16, 0))
        self._ui_outer = outer

        # Scrollable content area: every widget stays reachable on small windows
        self.app_scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        self.app_scroll.pack(fill="both", expand=True)

        # --- Header ---
        header = ctk.CTkFrame(self.app_scroll, corner_radius=14, fg_color=("#eef2f7", "#1b1f27"))
        header.pack(fill="x")

        self._build_header_logos(header)

        self.status_pill = ctk.CTkLabel(
            header,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=(GREEN, "#2a4a3c"),
            corner_radius=12,
            width=110,
            height=26,
        )
        self.status_pill.pack(side="right", padx=16, pady=14)

        # Language toggle
        lang_row = ctk.CTkFrame(header, fg_color="transparent")
        lang_row.pack(side="right", padx=(0, 8), pady=14)
        for code in ("en", "es"):
            active = code == self.lang
            ctk.CTkButton(
                lang_row,
                text=code.upper(),
                width=42,
                height=26,
                border_width=1,
                fg_color=("#3a8df0", "#2b6cb8") if active else "transparent",
                text_color="#ffffff" if active else GRAY,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda c=code: self._set_lang(c),
            ).pack(side="left", padx=2)

        # --- Mod folder ---
        folder_card = ctk.CTkFrame(self.app_scroll, corner_radius=14)
        folder_card.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            folder_card,
            text=self._tr("folder_label"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=GRAY,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        row = ctk.CTkFrame(folder_card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))

        self.folder_entry = ctk.CTkEntry(row, textvariable=self.mod_folder)
        self.folder_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            row, text=self._tr("browse"), width=110, command=self._browse_folder
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            row, text=self._tr("check_mod"), width=110, command=self._check_mod
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            folder_card,
            text=self._tr("folder_hint"),
            font=ctk.CTkFont(size=11),
            text_color=GRAY,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # --- Port readiness (live analysis of the selected mod) ---
        readiness_card = ctk.CTkFrame(self.app_scroll, corner_radius=14)
        readiness_card.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            readiness_card,
            text=self._tr("rdy_title"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=GRAY,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.readiness_grid = ctk.CTkFrame(readiness_card, fg_color="transparent")
        self.readiness_grid.pack(fill="x", padx=16, pady=(0, 12))
        self._update_readiness()

        # --- Steps ---
        self.steps_scroll = ctk.CTkScrollableFrame(
            self.app_scroll,
            label_text=self._tr("steps_label"),
            label_font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=14,
            height=190,
        )
        self.steps_scroll.pack(fill="x", pady=(12, 0))

        self.step_container = ctk.CTkFrame(self.steps_scroll, fg_color="transparent")
        self.step_container.pack(fill="x", padx=8, pady=6)

        sel_row = ctk.CTkFrame(self.app_scroll, fg_color="transparent")
        sel_row.pack(fill="x", pady=(2, 0))
        ctk.CTkButton(sel_row, text=self._tr("check_all"), width=100, height=26,
                      fg_color="transparent", border_width=1,
                      command=self._check_all).pack(side="right")
        ctk.CTkButton(sel_row, text=self._tr("uncheck_all"), width=100, height=26,
                      fg_color="transparent", border_width=1,
                      command=self._uncheck_all).pack(side="right", padx=(0, 8))

        # --- Log ---
        log_card = ctk.CTkFrame(self.app_scroll, corner_radius=14)
        log_card.pack(fill="both", expand=True, pady=(12, 0))

        ctk.CTkLabel(
            log_card,
            text=self._tr("log_label"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=GRAY,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.log_text = ctk.CTkTextbox(
            log_card,
            font=ctk.CTkFont(family="monospace", size=12),
            wrap="word",
            corner_radius=10,
            height=200,
        )
        self.log_text.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self._style_log_textbox(self.log_text)
        self.main_log_text = self.log_text
        self.log_target = self.log_text

        # --- Bottom bar (fixed, outside the scroll area) ---
        bottom = ctk.CTkFrame(outer, fg_color="transparent")
        bottom.pack(fill="x", pady=(12, 16))

        self.progress = ctk.CTkProgressBar(bottom, height=10, corner_radius=5)
        self.progress.set(0.0)  # ctk 6.0 defaults to 0.5; force empty on startup
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 16))

        self.pct_label = ctk.CTkLabel(bottom, text="0%", width=40,
                                      text_color=GRAY)
        self.pct_label.pack(side="left", padx=(0, 16))

        self.assets_btn = ctk.CTkButton(bottom, text=self._tr("assets_preview"), width=90,
                                        fg_color="transparent", border_width=1,
                                        command=self._preview_assets)
        self.assets_btn.pack(side="right", padx=(8, 0))

        self.save_log_btn = ctk.CTkButton(bottom, text=self._tr("save_log"), width=100,
                                          fg_color="transparent", border_width=1,
                                          command=self._save_log)
        self.save_log_btn.pack(side="right", padx=(8, 0))

        self.open_btn = ctk.CTkButton(bottom, text=self._tr("open_folder"), width=120,
                                      fg_color="transparent", border_width=1,
                                      state="disabled", command=self._open_folder)
        self.open_btn.pack(side="right", padx=(8, 0))

        self.turbowarp_btn = ctk.CTkButton(bottom, text=self._tr("open_turbowarp"), width=150,
                                           fg_color="transparent", border_width=1,
                                           state="disabled",
                                           command=self._open_turbowarp)
        self.turbowarp_btn.pack(side="right", padx=(8, 0))

        self.cancel_btn = ctk.CTkButton(bottom, text=self._tr("cancel"), width=110,
                                        fg_color=RED, hover_color="#b84545",
                                        state="disabled", command=self._request_cancel)
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.ffmpeg_btn = ctk.CTkButton(bottom, text=self._tr("ffmpeg_missing"), width=150,
                                        fg_color=YELLOW, hover_color="#c99f3a",
                                        text_color="#1b1f27",
                                        command=self._show_ffmpeg_help)
        if self._ffmpeg_ok:
            self.ffmpeg_btn.pack_forget()
        else:
            self.ffmpeg_btn.pack(side="right", padx=(8, 0))

        self.run_btn = ctk.CTkButton(bottom, text=self._tr("run"), width=130,
                                     fg_color=GREEN, hover_color="#25885e",
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._start_pipeline)
        self.run_btn.pack(side="right")

    def _style_log_textbox(self, tb):
        tb.configure(state="disabled")
        tb.tag_config("step", foreground="#7cc4ff")
        tb.tag_config("error", foreground=RED)
        tb.tag_config("warn", foreground=YELLOW)
        tb.tag_config("ok", foreground=GREEN)
        tb.tag_config("dim", foreground=GRAY)

    def _build_overlay(self):
        """Black loading screen: white bar at bottom + BF running above it."""
        self.overlay = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.overlay.place_forget()

        self.overlay_bar = ctk.CTkProgressBar(
            self.overlay,
            corner_radius=0,
            fg_color="#1e1e1e",
            progress_color="#ffffff",
        )
        self.overlay_bar.place(relx=0, rely=1.0, relwidth=1.0, relheight=0.05,
                               anchor="sw")

        self.bf_label = ctk.CTkLabel(self.overlay, text="",
                                     width=self.bf_display_w,
                                     height=self.bf_display_h)

        self.overlay_cancel = ctk.CTkButton(
            self.overlay,
            text=self._tr("cancel_x"),
            width=90,
            height=30,
            fg_color="#222222",
            hover_color="#333333",
            command=self._request_cancel,
        )
        self.overlay_cancel.place(relx=1.0, rely=0.0, anchor="ne", x=-14, y=14)

    def _load_bf_frames(self):
        """Load RuningBF.gif frames as CTkImages for the loading animation."""
        try:
            from PIL import ImageSequence

            gif_path = os.path.join(ASSETS_DIR, "RuningBF.gif")
            im = Image.open(gif_path)
            ratio = self.bf_display_w / im.size[0]
            new_h = max(1, int(im.size[1] * ratio))
            self.bf_display_h = new_h
            if hasattr(self, "bf_label"):
                self.bf_label.configure(width=self.bf_display_w,
                                        height=new_h)
            for frame in ImageSequence.Iterator(im):
                f = frame.convert("RGBA").resize(
                    (self.bf_display_w, new_h), Image.Resampling.LANCZOS
                )
                self.bf_frames.append(
                    ctk.CTkImage(light_image=f, dark_image=f,
                                 size=(self.bf_display_w, new_h))
                )
        except Exception as exc:
            print(f"BF GIF load failed: {exc!r}")

    def _update_bf_position(self, frac):
        if not self.bf_label.winfo_exists():
            return
        # BF stays above the bar, moving with the load; ends at the bar's right end
        relx = 0.05 + frac * 0.90
        self.bf_label.place(relx=relx, rely=0.93, anchor="s")

    def _start_bf_anim(self):
        if self.bf_frames:
            self.bf_label.configure(image=self.bf_frames[0])
            self.bf_frame_idx = 0
            self._animate_bf()

    def _stop_bf_anim(self):
        if self.bf_anim_job:
            self.after_cancel(self.bf_anim_job)
            self.bf_anim_job = None

    def _animate_bf(self):
        if not self.bf_frames or not self.bf_label.winfo_exists():
            return
        self.bf_frame_idx = (self.bf_frame_idx + 1) % len(self.bf_frames)
        self.bf_label.configure(image=self.bf_frames[self.bf_frame_idx])
        self.bf_anim_job = self.after(45, self._animate_bf)

    def _enter_loading(self):
        self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.overlay.lift()
        self.overlay_bar.set(0.0)
        self._update_bf_position(0.0)
        self._start_bf_anim()

        self.log_win = ctk.CTkToplevel(self)
        self.log_win.title(self._tr("app_log_title"))
        self.log_win.geometry("720x520")
        self.log_win.minsize(480, 320)
        self.log_win.configure(fg_color="#111111")

        self.log_target = ctk.CTkTextbox(
            self.log_win,
            font=ctk.CTkFont(family="monospace", size=12),
            wrap="word",
            corner_radius=10,
        )
        self.log_target.pack(fill="both", expand=True, padx=12, pady=12)
        self._style_log_textbox(self.log_target)

        self._play_music()

    def _exit_loading(self):
        self._stop_bf_anim()
        self._stop_tween()
        self._stop_music()
        self.overlay.place_forget()
        if getattr(self, "log_win", None) and self.log_win.winfo_exists():
            self.log_win.destroy()
        self.log_target = self.main_log_text

    def _stage_toolkit(self, folder):
        """Copy missing toolkit scripts (and blank .sb3) into the mod folder.

        The original tool requires all files to live inside the mod root;
        this automates that setup step.
        """
        staged = []
        for name in PREREQUISITE_SCRIPTS + ["port.py"]:
            dest = os.path.join(folder, name)
            if os.path.exists(dest):
                continue
            src = os.path.join(DEFAULT_FOLDER, name)
            if not os.path.exists(src):
                self.log(f"Warning: toolkit file not found in tool folder: {name}", "warn")
                continue
            shutil.copy2(src, dest)
            staged.append(name)

        # Blank .sb3 template: only when the mod folder has none at all
        if not _safe_glob(folder, "*.sb3"):
            blanks = _safe_glob(DEFAULT_FOLDER, "*.sb3")
            if blanks:
                dest = os.path.join(folder, os.path.basename(blanks[0]))
                if not os.path.exists(dest):
                    shutil.copy2(blanks[0], dest)
                    staged.append(os.path.basename(blanks[0]))
        return staged

    def _refresh_steps(self):
        for widget in self.step_container.winfo_children():
            widget.destroy()
        self.step_vars.clear()

        folder = self._resolve_mod_root(self.mod_folder.get())[0] \
            or self.mod_folder.get().strip()
        found = 0

        for i, script in enumerate(PREREQUISITE_SCRIPTS):
            var = ctk.BooleanVar(value=True)
            exists = os.path.exists(os.path.join(folder, script))
            if exists:
                found += 1

            cb = ctk.CTkCheckBox(
                self.step_container,
                text=script if exists else f"{script}  {self._tr('auto_tag')}",
                variable=var,
                font=ctk.CTkFont(size=13),
                checkbox_width=20,
                checkbox_height=20,
            )
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=3)
            if not exists:
                cb.configure(text_color=GRAY)
            self.step_vars[script] = var

        self.build_var = ctk.BooleanVar(value=True)
        build_cb = ctk.CTkCheckBox(
            self.step_container,
            text=self._tr("build_step"),
            variable=self.build_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            checkbox_width=20,
            checkbox_height=20,
        )
        build_cb.grid(row=(len(PREREQUISITE_SCRIPTS) + 1) // 2, column=0,
                      sticky="w", padx=(0, 24), pady=(8, 3))
        self.build_var_check = build_cb

        if found == 0:
            self.log(self._tr("no_prereq_warn"), "warn")

    def _check_all(self):
        for var in self.step_vars.values():
            var.set(True)
        self.build_var.set(True)

    def _uncheck_all(self):
        for var in self.step_vars.values():
            var.set(False)
        self.build_var.set(False)

    # ---------- Events ----------

    def _save_log(self):
        if not self.log_buffer:
            messagebox.showinfo(
                self._tr("save_log_title"), self._tr("save_log_empty")
            )
            return
        path = filedialog.asksaveasfilename(
            title=self._tr("save_log_title"),
            defaultextension=".txt",
            initialfile="psychtobasic_log.txt",
            initialdir=GENERATED_DIR,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(line for line, _ in self.log_buffer) + "\n")
        except OSError as exc:
            messagebox.showerror(self._tr("save_log_title"), str(exc))
            return
        self.log(f"Log saved: {path}", "step")

    def _schedule_readiness(self, *_):
        if self._readiness_job:
            self.after_cancel(self._readiness_job)
        self._readiness_job = self.after(250, self._update_readiness)

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.mod_folder.get())
        if chosen:
            self.mod_folder.set(chosen)
            self._save_config(chosen)
            self._refresh_steps()

    def _open_folder(self):
        folder = self.mod_folder.get()
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            messagebox.showerror(self._tr("open_folder"), str(exc))

    # ---------- Logging (thread-safe via queue) ----------

    def log(self, line, kind="normal"):
        self.log_queue.put((str(line), kind))
        self.log_buffer.append((str(line), kind))

    def _drain_queue(self):
        try:
            while True:
                line, kind = self.log_queue.get_nowait()
                target = self.log_target
                if not target.winfo_exists():
                    continue
                target.configure(state="normal")
                target.insert("end", line + "\n", kind)
                target.see("end")
                target.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _set_status(self, text, color=None):
        if color is not None:
            self.status_pill.configure(fg_color=color)
        self.status_var.set(text)

    def _set_step_expected(self, idx, total):
        """Raise the creep ceiling toward the end of the step about to run."""
        self._step_end = idx / total if total else 0.0
        if self._step_end > 1.0:
            self._step_end = 1.0

    def _set_progress(self, idx, total):
        """Real progress landed: the tween will glide toward this value."""
        self.progress_target = idx / total if total else 0.0
        if self._step_end is not None:
            self._step_end = self.progress_target

    def _apply_progress(self, frac):
        self.overlay_bar.set(frac)
        self.progress.set(frac)
        self.pct_label.configure(text=f"{int(frac * 100)}%")
        self._update_bf_position(frac)

    def _start_tween(self):
        self.pipeline_running = True
        if self.tween_job is None:
            self._tick_progress()

    def _stop_tween(self):
        self.pipeline_running = False
        if self.tween_job:
            self.after_cancel(self.tween_job)
            self.tween_job = None

    def _tick_progress(self):
        if not self.pipeline_running:
            self.tween_job = None
            return

        # Smooth glide toward the real landed progress
        target = self.progress_target
        if self._step_end is not None:
            # Gentle creep toward the running step's end (never quite reaching)
            creep = min(self._step_end - 0.006, 0.994)
            if creep < 0:
                creep = 0.0
            target = max(target, creep)

        d = self.progress_display
        d += (target - d) * 0.15
        if abs(target - d) < 0.002:
            d = target
        self.progress_display = d
        self._apply_progress(d)

        self.tween_job = self.after(40, self._tick_progress)

    def _set_running(self, running):
        state = "disabled" if running else "normal"
        self.run_btn.configure(state=state)
        self.cancel_btn.configure(state="normal" if running else "disabled")
        self.open_btn.configure(state="normal" if not running else "disabled")
        self.turbowarp_btn.configure(state="normal" if not running else "disabled")

    # ---------- Mod analysis ----------

    def _resolve_mod_root(self, folder):
        """Find the actual mod root.

        Accepted: the folder itself when it has pack.png, or a folder with
        exactly ONE child that has pack.png (e.g. the project root holding
        one mod). Returns (root_path, note) or (None, reason).
        """
        folder = (folder or "").strip()
        if os.path.isdir(folder) and os.path.exists(
            os.path.join(folder, "pack.png")
        ):
            return folder, ""
        if os.path.isdir(folder):
            candidates = [
                os.path.join(folder, name)
                for name in os.listdir(folder)
                if os.path.isdir(os.path.join(folder, name))
                and os.path.exists(os.path.join(folder, name, "pack.png"))
            ]
            if len(candidates) == 1:
                return candidates[0], os.path.basename(candidates[0])
            if len(candidates) > 1:
                return None, "multiple mods inside — select the mod folder itself"
        return None, "no pack.png here or one level below"

    def _scan_mod(self, root):
        """Count every resource the port pipeline consumes (old + new layouts)."""

        def collect(dirpath, exts, recursive=False):
            if not os.path.isdir(dirpath):
                return []
            matches = []
            for dirpath2, _dirs, files in os.walk(dirpath):
                for f in files:
                    if f.lower().endswith(exts):
                        matches.append(os.path.join(dirpath2, f))
                if not recursive:
                    break
            return matches

        def charts(dirpath):
            if not os.path.isdir(dirpath):
                return []
            out = []
            excluded = ("metadata", "dialog", "events")

            def clean(paths):
                return [
                    f for f in paths
                    if not any(x in os.path.basename(f).lower() for x in excluded)
                ]

            # Old layout: each song lives as data/<song>/<chart>.json
            category_dirs = {
                "characters", "songs", "weeks", "stages", "dialogs",
                "images", "backgrounds", "fonts", "splashes", "menu",
            }
            for entry in os.scandir(dirpath):
                if not entry.is_dir() or entry.name.lower() in category_dirs:
                    continue
                out.extend(clean(collect(entry.path, (".json",))))
            # Root-level chart jsons can live directly in data/
            out.extend(charts_root(dirpath))
            return out

        def charts_root(dirpath):
            if not os.path.isdir(dirpath):
                return []
            out = []
            for f in os.listdir(dirpath):
                if not f.lower().endswith(".json"):
                    continue
                if any(x in f.lower() for x in ("metadata", "dialog", "events")):
                    continue
                out.append(os.path.join(dirpath, f))
            return out

        def clean(paths):
            return [
                f for f in paths
                if not any(
                    x in os.path.basename(f).lower()
                    for x in ("metadata", "dialog", "events")
                )
            ]

        scan = {
            "pack": os.path.exists(os.path.join(root, "pack.png")),
            "weeks": collect(os.path.join(root, "weeks"), (".json",))
                     + collect(os.path.join(root, "data", "weeks"), (".json",)),
            "chars": collect(os.path.join(root, "characters"), (".json",))
                     + collect(os.path.join(root, "data", "characters"), (".json",), recursive=True),
            "charts": charts(os.path.join(root, "data"))
                      + clean(collect(os.path.join(root, "data", "songs"), (".json",), recursive=True)),
            "audio": collect(os.path.join(root, "songs"), (".ogg", ".mp3", ".wav"), recursive=True)
                     + collect(os.path.join(root, "data", "songs"), (".ogg", ".mp3", ".wav"), recursive=True),
            "stages": collect(os.path.join(root, "stages"), (".json",))
                      + collect(os.path.join(root, "data", "stages"), (".json",)),
            "icons": collect(os.path.join(root, "characters"), (".png",))
                     + collect(os.path.join(root, "data", "characters"), (".png",), recursive=True),
            "notes": collect(os.path.join(root, "custom_notetypes"), (".json",)),
            "noteskins": collect(os.path.join(root, "noteskins"), (".png", ".json"), recursive=True),
            "template": _safe_glob(root, "*.sb3"),
        }
        return scan

    def _update_readiness(self):
        self._readiness_job = None
        card = getattr(self, "readiness_grid", None)
        if card is None or not card.winfo_exists():
            return
        for w in card.winfo_children():
            w.destroy()

        folder = self.mod_folder.get().strip()
        root, note = self._resolve_mod_root(folder)
        if root is None:
            ctk.CTkLabel(
                card,
                text=f"{self._tr('rdy_no_mod')} — {note}",
                text_color=RED,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=(0, 24), pady=2)
            return

        scan = self._scan_mod(root)
        if note:
            self.log(self._tr("rdy_auto", name=note), "dim")

        rows = [
            ("rdy_root", root is not None, os.path.basename(root)),
            ("rdy_weeks", bool(scan["weeks"]), len(scan["weeks"])),
            ("rdy_chars", bool(scan["chars"]), len(scan["chars"])),
            ("rdy_charts", bool(scan["charts"]), len(scan["charts"])),
            ("rdy_audio", bool(scan["audio"]), len(scan["audio"])),
            ("rdy_stages", bool(scan["stages"]), len(scan["stages"])),
            ("rdy_icons", bool(scan["icons"]), len(scan["icons"])),
            ("rdy_notes", bool(scan["notes"]), len(scan["notes"])),
            ("rdy_noteskins", bool(scan["noteskins"]), len(scan["noteskins"])),
            ("rdy_template", bool(scan["template"]), 1 if scan["template"] else 0),
            ("rdy_ffmpeg", self._check_ffmpeg(), None),
        ]

        for i, (key, ok, count) in enumerate(rows):
            label = self._tr(key)
            color = GREEN if ok else RED
            text = f"{'✓' if ok else '✗'} {label}"
            if count is not None:
                text += f": {count}" if ok else " — 0"
            ctk.CTkLabel(
                card,
                text=text,
                text_color=color,
                font=ctk.CTkFont(size=12, weight="bold" if key == "rdy_root" else "normal"),
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=2)

        missing = [
            self._tr(key)
            for key, ok, _ in rows
            if not ok and key not in ("rdy_root", "rdy_template", "rdy_ffmpeg")
        ]
        verdict_key = "rdy_verdict_yes"
        if missing:
            verdict_key = "rdy_verdict_no" if not scan["chars"] or not scan["weeks"] or not scan["charts"] else "rdy_verdict_partial"
        verdict = self._tr(verdict_key, missing=", ".join(missing))
        ctk.CTkLabel(
            card,
            text=verdict,
            text_color=(GREEN, "#4ade80") if verdict_key == "rdy_verdict_yes" else YELLOW,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=(len(rows) + 1) // 2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    # ---------- Pipeline ----------

    def _start_pipeline(self):
        folder_raw = self.mod_folder.get().strip()
        root, note = self._resolve_mod_root(folder_raw)
        if root is None:
            messagebox.showerror(
                self._tr("err_title"),
                f"{self._tr('rdy_no_mod')} — {note}",
            )
            return
        folder = root
        if note:
            self.log(self._tr("rdy_auto", name=note), "dim")

        self._save_config(folder)

        staged = self._stage_toolkit(folder)
        if staged:
            self.log(
                self._tr(
                    "staged_log",
                    n=len(staged),
                    names=", ".join(staged),
                ),
                "step",
            )

        steps = [s for s, v in self.step_vars.items() if v.get()]
        if self.build_var.get():
            steps.append("BUILD_SB3")

        if not steps:
            messagebox.showwarning(
                self._tr("no_steps_title"), self._tr("no_steps_body")
            )
            return

        if "BUILD_SB3" in steps:
            sb3 = _safe_glob(folder, "*.sb3")
            if not sb3:
                answer = messagebox.askyesno(
                    self._tr("no_sb3_title"),
                    self._tr("no_sb3_body"),
                )
                if not answer:
                    return

        self.progress_target = 0.0
        self.progress_display = 0.0
        self._step_end = None
        self._apply_progress(0.0)
        self.cancel_requested = False
        self._set_running(True)
        self._set_status(self._tr("status_running"), GREEN)
        self._enter_loading()
        self._start_tween()

        self.log("=" * 60, "dim")
        self.log(f"Mod folder : {folder}", "dim")
        self.log(f"Steps      : {', '.join(steps)}", "dim")
        self.log("=" * 60, "dim")

        self.worker = threading.Thread(
            target=self._run_pipeline, args=(folder, steps), daemon=True
        )
        self.worker.start()

    def _check_mod(self):
        """Scan the selected mod folder and report health in the log."""
        folder_raw = self.mod_folder.get().strip()
        folder, note = self._resolve_mod_root(folder_raw)
        if folder is None:
            messagebox.showerror(
                self._tr("check_mod_title"),
                f"{self._tr('rdy_no_mod')} — {note}",
            )
            return

        data = os.path.join(folder, "data")

        def report(label, ok, detail=""):
            kind = "ok" if ok else "warn"
            tag = "OK  " if ok else "MISS"
            text = f"  [{tag}] {label}"
            if detail:
                text += f" — {detail}"
            self.log(text, kind)

        self.log("=" * 60, "dim")
        self.log(self._tr("mod_check_header", folder=folder), "dim")

        report(self._tr("ck_pack"), os.path.exists(os.path.join(folder, "pack.png")))

        for key, sub in (("ck_chars", "characters"), ("ck_songs", "songs"), ("ck_weeks", "weeks")):
            d = os.path.join(data, sub)
            jsons = _safe_glob(d, "*.json") if os.path.isdir(d) else []
            report(self._tr(key), len(jsons) > 0, self._tr("ck_found", n=len(jsons)))

        missing = [
            n for n in PREREQUISITE_SCRIPTS + ["port.py"]
            if not os.path.exists(os.path.join(folder, n))
        ]
        report(self._tr("ck_toolkit"), not missing,
               self._tr("ck_missing", list=", ".join(missing)) if missing
               else self._tr("ck_present"))

        sb3 = _safe_glob(folder, "*.sb3")
        report(self._tr("ck_sb3"), bool(sb3),
               os.path.basename(sb3[0]) if sb3 else "")

        songs_data = os.path.join(data, "songs")
        audios = (_safe_glob(songs_data, "*", recursive=True)
                  if os.path.isdir(songs_data) else [])
        audio_count = sum(
            1 for f in audios if f.lower().endswith((".ogg", ".mp3", ".wav"))
        )
        report(self._tr("ck_audio"), audio_count > 0,
               self._tr("ck_found", n=audio_count))

        chars_data = os.path.join(data, "characters")
        icons = (_safe_glob(chars_data, "*.png", recursive=True)
                 if os.path.isdir(chars_data) else [])
        report(self._tr("ck_icons"), len(icons) > 0,
               self._tr("ck_found", n=len(icons)))

        report(self._tr("ck_ffmpeg"), self._check_ffmpeg())

        self.log(self._tr("mod_check_done"), "step")

    def _ensure_local_server(self, directory):
        """Serve `directory` on 127.0.0.1 (CORS enabled); reuse an existing one."""
        if self._http_server is not None and self._server_dir == directory:
            return self._http_port
        if self._http_server is not None:
            daemon = threading.Thread(
                target=self._http_server.shutdown, daemon=True
            )
            daemon.start()
            self._http_server = None
        try:
            handler = partial(_CORSHandler, directory=directory)
            self._http_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        except OSError as exc:
            self.log(f"Local server failed: {exc}", "warn")
            return None
        self._server_dir = directory
        self._http_port = self._http_server.server_address[1]
        threading.Thread(
            target=self._http_server.serve_forever, daemon=True
        ).start()
        self.log(f"Local server on http://127.0.0.1:{self._http_port}", "dim")
        return self._http_port

    def _open_turbowarp(self):
        """Load the built .sb3 in TurboWarp through a local (CORS) file server.

        TurboWarp can only link to projects that exist at a URL, so we serve
        the file locally and point ?project= at 127.0.0.1.
        """
        files = sorted(_safe_glob(GENERATED_DIR, "built_*.sb3"))
        if not files:
            root = self._resolve_mod_root(self.mod_folder.get())[0] \
                or self.mod_folder.get().strip()
            files = sorted(_safe_glob(root, "built_*.sb3"))
        if not files:
            messagebox.showinfo(
                self._tr("turbowarp_title"),
                self._tr("turbowarp_no_build"),
            )
            return
        directory = os.path.dirname(files[-1])
        port = self._ensure_local_server(directory)
        if not port:
            messagebox.showerror(
                self._tr("turbowarp_title"),
                self._tr("turbowarp_server_fail"),
            )
            return
        name = os.path.basename(files[-1])
        url = f"https://turbowarp.org/editor?project=http://127.0.0.1:{port}/{name}"
        self.log(f"Opening TurboWarp with local project: {url}", "step")
        webbrowser.open(url)

    def _collect_outputs(self, folder):
        """Copy build artifacts into the local generated/ folder and verify them."""
        os.makedirs(GENERATED_DIR, exist_ok=True)
        for src in _safe_glob(folder, "built_*.sb3"):
            try:
                dst = os.path.join(GENERATED_DIR, os.path.basename(src))
                shutil.copy2(src, dst)
                self.log(f"Collected {os.path.basename(src)} -> generated/", "step")
            except OSError as exc:
                self.log(f"Collect failed: {exc}", "warn")
                continue
            try:
                with zipfile.ZipFile(dst) as zf:
                    bad = zf.testzip()
                    entries = len(zf.namelist())
                    size = os.path.getsize(dst)
                if bad is None:
                    self.log(
                        f"Verify OK: {os.path.basename(dst)} "
                        f"({size / 1e6:.1f} MB, {entries} files)",
                        "ok",
                    )
                else:
                    self.log(
                        f"Verify WARNING: corrupt entry {bad!r} in "
                        f"{os.path.basename(dst)}",
                        "warn",
                    )
            except zipfile.BadZipFile:
                self.log(
                    f"Verify ERROR: {os.path.basename(dst)} is not a valid "
                    ".sb3 (zip) file.",
                    "error",
                )

    def _run_pipeline(self, folder, steps):
        try:
            for idx, step in enumerate(steps, start=1):
                if self.cancel_requested:
                    self.log(self._tr("pipeline_cancelled"), "warn")
                    self._set_status(self._tr("status_cancelled"), YELLOW)
                    self._finish(None)
                    return

                if step == "BUILD_SB3":
                    label = self._tr("build_step")
                    command = [sys.executable, "-c", "import port; port.process_sb3()"]
                else:
                    label = self._tr("run_step", step=step)
                    command = [sys.executable, step]

                self._set_status(f"[{idx}/{len(steps)}] {label}")
                self._set_step_expected(idx, len(steps))
                self.log(f"\n>>> {label}", "step")

                code = self._run_command(folder, command)

                if self.cancel_requested:
                    self.log(self._tr("pipeline_cancelled"), "warn")
                    self._set_status(self._tr("status_cancelled"), YELLOW)
                    self._finish(None)
                    return

                if code != 0:
                    self.log(self._tr("step_failed", step=step, code=code), "error")
                    self._set_progress(idx, len(steps))
                    self._set_status(self._tr("status_failed"), RED)
                    self._finish(
                        False,
                        self._tr("finish_failed_step", step=step, code=code),
                    )
                    return

                self._set_progress(idx, len(steps))

            self._collect_outputs(folder)
            self.log("\n--- Pipeline finished successfully ---", "ok")
            self._set_status(self._tr("status_done"), GREEN)
            self._finish(True, self._tr("finish_success"))
        except Exception as exc:
            self.log(f"\n!!! ERROR: {exc}", "error")
            self._set_status(self._tr("status_error"), RED)
            self._finish(False, self._tr("internal_error", exc=exc), is_error=True)

    def _run_command(self, folder, command):
        """Run one command, streaming its output into the log. Returns exit code."""
        try:
            self.proc = subprocess.Popen(
                command,
                cwd=folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            self.log(f"!!! Could not start: {command[0]}", "error")
            return 1
        except Exception as exc:
            self.log(f"!!! Could not start process: {exc}", "error")
            return 1

        for raw_line in self.proc.stdout:
            line = raw_line.rstrip("\n")
            if line.strip():
                kind = "error" if "error" in line.lower() or "warning" in line.lower() else "normal"
                self.log(f"  {line}", kind)
            if self.cancel_requested:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()

        self.proc.wait()
        return self.proc.returncode

    def _request_cancel(self):
        self.cancel_requested = True
        self._set_status(self._tr("status_cancelling"))

    def _finish(self, ok, message=None, is_error=False):
        def show():
            self._set_running(False)
            self._exit_loading()
            if ok is None:
                return
            if is_error:
                messagebox.showerror(self._tr("err_title"), message)
            elif ok:
                messagebox.showinfo(self._tr("done_title"), message)

        self.after(0, show)


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = PortGUI()
    app.mainloop()


if __name__ == "__main__":
    main()