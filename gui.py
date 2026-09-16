"""Psychto Basic - Mod Port GUI (modern customtkinter build)

Graphical wrapper around the FNF (Psych Engine) mod -> Scratch (.sb3) port pipeline.
Runs the same scripts as port.py but step by step, with a live colorized log,
progress tracking, and cancel support.
"""

import glob
import os
import queue
import shutil
import subprocess
import sys
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

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

        self._build_ui()
        self._build_overlay()
        self._load_bf_frames()
        self._refresh_steps()

        self.after(100, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._stop_music()
        self.destroy()

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
            for f in glob.glob(os.path.join(ASSETS_DIR, "Music", "*"))
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
        self.mod_folder = ctk.StringVar(value=DEFAULT_FOLDER)
        self.step_vars = {}
        self.status_var = ctk.StringVar(value="Ready")
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
            text=APP_TITLE,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left", padx=(18, 0), pady=14)
        ctk.CTkLabel(
            header,
            text=APP_SUBTITLE,
            font=ctk.CTkFont(size=13),
            text_color=GRAY,
        ).pack(side="left", padx=(12, 0), pady=14)

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=18, pady=(16, 0))

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

        # --- Mod folder ---
        folder_card = ctk.CTkFrame(self.app_scroll, corner_radius=14)
        folder_card.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            folder_card,
            text="Mod folder",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=GRAY,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        row = ctk.CTkFrame(folder_card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))

        self.folder_entry = ctk.CTkEntry(row, textvariable=self.mod_folder)
        self.folder_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            row, text="Browse...", width=110, command=self._browse_folder
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            folder_card,
            text="Mod root folder (pack.png). Missing toolkit files are auto-staged on Run.",
            font=ctk.CTkFont(size=11),
            text_color=GRAY,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # --- Steps ---
        self.steps_scroll = ctk.CTkScrollableFrame(
            self.app_scroll,
            label_text="Steps to run",
            label_font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=14,
            height=190,
        )
        self.steps_scroll.pack(fill="x", pady=(12, 0))

        self.step_container = ctk.CTkFrame(self.steps_scroll, fg_color="transparent")
        self.step_container.pack(fill="x", padx=8, pady=6)

        sel_row = ctk.CTkFrame(self.app_scroll, fg_color="transparent")
        sel_row.pack(fill="x", pady=(2, 0))
        ctk.CTkButton(sel_row, text="Check all", width=100, height=26,
                      fg_color="transparent", border_width=1,
                      command=self._check_all).pack(side="right")
        ctk.CTkButton(sel_row, text="Uncheck all", width=100, height=26,
                      fg_color="transparent", border_width=1,
                      command=self._uncheck_all).pack(side="right", padx=(0, 8))

        # --- Log ---
        log_card = ctk.CTkFrame(self.app_scroll, corner_radius=14)
        log_card.pack(fill="both", expand=True, pady=(12, 0))

        ctk.CTkLabel(
            log_card,
            text="Log",
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

        self.open_btn = ctk.CTkButton(bottom, text="Open folder", width=120,
                                      fg_color="transparent", border_width=1,
                                      state="disabled", command=self._open_folder)
        self.open_btn.pack(side="right", padx=(8, 0))

        self.cancel_btn = ctk.CTkButton(bottom, text="Cancel", width=110,
                                        fg_color=RED, hover_color="#b84545",
                                        state="disabled", command=self._request_cancel)
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.run_btn = ctk.CTkButton(bottom, text="▶  Run", width=130,
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
            text="✖ Cancel",
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
        self.log_win.title("Psych To Basic — Log")
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
        if not glob.glob(os.path.join(folder, "*.sb3")):
            blanks = glob.glob(os.path.join(DEFAULT_FOLDER, "*.sb3"))
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

        folder = self.mod_folder.get()
        found = 0

        for i, script in enumerate(PREREQUISITE_SCRIPTS):
            var = ctk.BooleanVar(value=True)
            exists = os.path.exists(os.path.join(folder, script))
            if exists:
                found += 1

            cb = ctk.CTkCheckBox(
                self.step_container,
                text=script if exists else f"{script}  (auto)",
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
            text="Build Scratch project (.sb3)",
            variable=self.build_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            checkbox_width=20,
            checkbox_height=20,
        )
        build_cb.grid(row=(len(PREREQUISITE_SCRIPTS) + 1) // 2, column=0,
                      sticky="w", padx=(0, 24), pady=(8, 3))
        self.build_var_check = build_cb

        if found == 0:
            self.log("No prerequisite scripts yet — they will be auto-staged from the tool folder on Run.", "warn")

    def _check_all(self):
        for var in self.step_vars.values():
            var.set(True)
        self.build_var.set(True)

    def _uncheck_all(self):
        for var in self.step_vars.values():
            var.set(False)
        self.build_var.set(False)

    # ---------- Events ----------

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.mod_folder.get())
        if chosen:
            self.mod_folder.set(chosen)
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
            messagebox.showerror("Open folder", str(exc))

    # ---------- Logging (thread-safe via queue) ----------

    def log(self, line, kind="normal"):
        self.log_queue.put((str(line), kind))

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

    # ---------- Pipeline ----------

    def _start_pipeline(self):
        folder = self.mod_folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror("Error", f"Folder does not exist:\n{folder}")
            return

        staged = self._stage_toolkit(folder)
        if staged:
            self.log(
                f"Staged {len(staged)} toolkit file(s) into mod folder: "
                + ", ".join(staged),
                "step",
            )

        steps = [s for s, v in self.step_vars.items() if v.get()]
        if self.build_var.get():
            steps.append("BUILD_SB3")

        if not steps:
            messagebox.showwarning("No steps", "Select at least one step to run.")
            return

        if "BUILD_SB3" in steps:
            sb3 = glob.glob(os.path.join(folder, "*.sb3"))
            if not sb3:
                answer = messagebox.askyesno(
                    "No .sb3 found",
                    "No .sb3 project was found in the selected folder.\n"
                    "The build step will produce no output.\n\nContinue anyway?",
                )
                if not answer:
                    return

        self.progress_target = 0.0
        self.progress_display = 0.0
        self._step_end = None
        self._apply_progress(0.0)
        self.cancel_requested = False
        self._set_running(True)
        self._set_status("Running", GREEN)
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

    def _run_pipeline(self, folder, steps):
        try:
            for idx, step in enumerate(steps, start=1):
                if self.cancel_requested:
                    self.log("--- Pipeline cancelled by user ---", "warn")
                    self._set_status("Cancelled", YELLOW)
                    self._finish(None)
                    return

                if step == "BUILD_SB3":
                    label = "Building Scratch project (.sb3)"
                    command = [sys.executable, "-c", "import port; port.process_sb3()"]
                else:
                    label = f"Running {step}"
                    command = [sys.executable, step]

                self._set_status(f"[{idx}/{len(steps)}] {label}")
                self._set_step_expected(idx, len(steps))
                self.log(f"\n>>> {label}", "step")

                code = self._run_command(folder, command)

                if self.cancel_requested:
                    self.log("--- Pipeline cancelled by user ---", "warn")
                    self._set_status("Cancelled", YELLOW)
                    self._finish(None)
                    return

                if code != 0:
                    self.log(f"\n!!! STEP FAILED: '{step}' (exit code {code})", "error")
                    self._set_progress(idx, len(steps))
                    self._set_status("Failed", RED)
                    self._finish(False, f"Step '{step}' failed (exit code {code}).")
                    return

                self._set_progress(idx, len(steps))

            self.log("\n--- Pipeline finished successfully ---", "ok")
            self._set_status("Done", GREEN)
            self._finish(True, "Pipeline finished successfully.")
        except Exception as exc:
            self.log(f"\n!!! ERROR: {exc}", "error")
            self._set_status("Error", RED)
            self._finish(False, f"Internal error: {exc}", is_error=True)

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
        self._set_status("Cancelling...")

    def _finish(self, ok, message=None, is_error=False):
        def show():
            self._set_running(False)
            self._exit_loading()
            if ok is None:
                return
            if is_error:
                messagebox.showerror("Error", message)
            elif ok:
                messagebox.showinfo("Done", message)

        self.after(0, show)


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = PortGUI()
    app.mainloop()


if __name__ == "__main__":
    main()