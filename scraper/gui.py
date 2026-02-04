#!/usr/bin/env python3
"""
Jamabandi Land Records Scraper - GUI
=====================================
Tkinter GUI for configuring and running the HTTP scraper and PDF converter.
"""

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

SRC_DIR = Path(__file__).parent.resolve()  # scraper/ — where .py files live
PROJECT_DIR = SRC_DIR.parent.resolve()  # project root — data & config here
GUI_CONFIG_FILE = PROJECT_DIR / "gui_config.json"

DEFAULTS = {
    "district_code": "17",
    "tehsil_code": "102",
    "village_code": "",
    "period": "2024-2025",
    "khewat_start": 1,
    "khewat_end": 100,
    "save_path": "",
    "downloads_dir": "",
    "session_cookie": "",
    "progress_file": "progress.json",
    "concurrent_enabled": False,
    "concurrent_workers": 3,
    "min_delay": 1.0,
    "max_delay": 2.5,
    "max_retries": 3,
    "page_load_timeout": 30,
    "form_postback_sleep": 0.25,
    "auto_convert_pdf": True,
    "pdf_input_dir": "",
    "pdf_output_dir": "",
    "pdf_workers": 4,
}

ADVANCED_PASSWORD = "admin123"


class PasswordDialog(simpledialog.Dialog):
    """Simple password entry dialog."""

    def body(self, master):
        ttk.Label(master, text="Enter password to unlock advanced settings:").grid(
            row=0, column=0, columnspan=2, pady=(0, 8)
        )
        self.password_var = tk.StringVar()
        self.entry = ttk.Entry(
            master, textvariable=self.password_var, show="*", width=30
        )
        self.entry.grid(row=1, column=0, columnspan=2)
        return self.entry

    def apply(self):
        self.result = self.password_var.get()


class JamabandiGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Jamabandi Land Records Scraper")
        self.root.minsize(720, 820)
        self.root.geometry("780x920")

        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.advanced_unlocked = False

        # StringVar / IntVar / DoubleVar holders
        self.vars: dict[str, tk.Variable] = {}

        self._build_ui()
        self._load_config()

    # ─────────────────────────────────────────────────────────────────────
    # UI CONSTRUCTION
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style()
        style.configure("TLabelframe.Label", font=("", 11, "bold"))

        container = ttk.Frame(self.root, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        # ── Main Settings ──────────────────────────────────────────────
        main_frame = ttk.LabelFrame(container, text="Main Settings", padding=8)
        main_frame.pack(fill=tk.X, pady=(0, 6))

        row = 0
        for label, key, default, width in [
            ("District Code:", "district_code", DEFAULTS["district_code"], 12),
            ("Tehsil Code:", "tehsil_code", DEFAULTS["tehsil_code"], 12),
            ("Village Code:", "village_code", DEFAULTS["village_code"], 12),
            ("Period:", "period", DEFAULTS["period"], 16),
        ]:
            ttk.Label(main_frame, text=label).grid(
                row=row, column=0, sticky=tk.W, padx=(0, 4), pady=2
            )
            var = tk.StringVar(value=default)
            self.vars[key] = var
            ttk.Entry(main_frame, textvariable=var, width=width).grid(
                row=row, column=1, sticky=tk.W, pady=2
            )
            row += 1

        # Khewat range on same row
        ttk.Label(main_frame, text="Khewat Start:").grid(
            row=row, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_start = tk.IntVar(value=DEFAULTS["khewat_start"])
        self.vars["khewat_start"] = var_start
        ttk.Spinbox(
            main_frame, from_=1, to=99999, textvariable=var_start, width=10
        ).grid(row=row, column=1, sticky=tk.W, pady=2)
        ttk.Label(main_frame, text="Khewat End:").grid(
            row=row, column=2, sticky=tk.W, padx=(16, 4), pady=2
        )
        var_end = tk.IntVar(value=DEFAULTS["khewat_end"])
        self.vars["khewat_end"] = var_end
        ttk.Spinbox(main_frame, from_=1, to=99999, textvariable=var_end, width=10).grid(
            row=row, column=3, sticky=tk.W, pady=2
        )
        row += 1

        # Save Path (base directory for all downloads)
        ttk.Label(main_frame, text="Save Path:").grid(
            row=row, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_sp = tk.StringVar(value=DEFAULTS["save_path"])
        self.vars["save_path"] = var_sp
        ttk.Entry(main_frame, textvariable=var_sp, width=40).grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, pady=2
        )
        ttk.Button(
            main_frame, text="Browse...", command=lambda: self._browse_dir(var_sp)
        ).grid(row=row, column=3, sticky=tk.W, padx=(4, 0), pady=2)
        row += 1

        # Downloads folder name (created inside Save Path)
        ttk.Label(main_frame, text="Folder Name:").grid(
            row=row, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_dl = tk.StringVar(value=DEFAULTS["downloads_dir"])
        self.vars["downloads_dir"] = var_dl
        ttk.Entry(main_frame, textvariable=var_dl, width=30).grid(
            row=row, column=1, columnspan=2, sticky=tk.W, pady=2
        )
        ttk.Label(main_frame, text="(auto-generated if blank)").grid(
            row=row, column=3, sticky=tk.W, padx=(4, 0), pady=2
        )
        row += 1

        # Progress file
        ttk.Label(main_frame, text="Progress File:").grid(
            row=row, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_pf = tk.StringVar(value=DEFAULTS["progress_file"])
        self.vars["progress_file"] = var_pf
        ttk.Entry(main_frame, textvariable=var_pf, width=30).grid(
            row=row, column=1, columnspan=2, sticky=tk.W, pady=2
        )
        row += 1

        # Session cookie (full width)
        ttk.Label(main_frame, text="Session Cookie:").grid(
            row=row, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_cookie = tk.StringVar(value=DEFAULTS["session_cookie"])
        self.vars["session_cookie"] = var_cookie
        ttk.Entry(main_frame, textvariable=var_cookie, width=60).grid(
            row=row, column=1, columnspan=3, sticky=tk.EW, pady=2
        )
        row += 1

        # ── Concurrent Downloads ──────────────────────────────────────
        conc_sep = ttk.Separator(main_frame, orient=tk.HORIZONTAL)
        conc_sep.grid(row=row, column=0, columnspan=4, sticky=tk.EW, pady=(6, 4))
        row += 1

        var_conc = tk.BooleanVar(value=DEFAULTS["concurrent_enabled"])
        self.vars["concurrent_enabled"] = var_conc
        self.conc_check = ttk.Checkbutton(
            main_frame,
            text="Enable Concurrent Downloads",
            variable=var_conc,
            command=self._toggle_concurrent,
        )
        self.conc_check.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=2)

        ttk.Label(main_frame, text="Workers:").grid(
            row=row, column=2, sticky=tk.E, padx=(4, 4), pady=2
        )
        var_cw = tk.IntVar(value=DEFAULTS["concurrent_workers"])
        self.vars["concurrent_workers"] = var_cw
        self.conc_workers_spin = ttk.Spinbox(
            main_frame,
            from_=3,
            to=8,
            textvariable=var_cw,
            width=6,
            state="disabled",
        )
        self.conc_workers_spin.grid(row=row, column=3, sticky=tk.W, pady=2)
        row += 1

        main_frame.columnconfigure(1, weight=1)

        # ── Advanced Settings ──────────────────────────────────────────
        adv_frame = ttk.LabelFrame(
            container, text="Advanced Settings (locked)", padding=8
        )
        adv_frame.pack(fill=tk.X, pady=(0, 6))
        self.adv_frame = adv_frame

        self.adv_widgets: list[ttk.Widget] = []

        adv_fields = [
            ("Min Delay (s):", "min_delay", DEFAULTS["min_delay"], "double"),
            ("Max Delay (s):", "max_delay", DEFAULTS["max_delay"], "double"),
            ("Max Retries:", "max_retries", DEFAULTS["max_retries"], "int"),
            (
                "Page Load Timeout (s):",
                "page_load_timeout",
                DEFAULTS["page_load_timeout"],
                "int",
            ),
            (
                "Form Postback Sleep (s):",
                "form_postback_sleep",
                DEFAULTS["form_postback_sleep"],
                "double",
            ),
        ]

        for i, (label, key, default, kind) in enumerate(adv_fields):
            ttk.Label(adv_frame, text=label).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 4), pady=2
            )
            if kind == "double":
                var = tk.DoubleVar(value=default)
            else:
                var = tk.IntVar(value=default)
            self.vars[key] = var
            widget = ttk.Spinbox(
                adv_frame,
                from_=0,
                to=9999 if kind == "int" else 999.0,
                increment=1 if kind == "int" else 0.25,
                textvariable=var,
                width=10,
                state="disabled",
            )
            widget.grid(row=i, column=1, sticky=tk.W, pady=2)
            self.adv_widgets.append(widget)

        self.unlock_btn = ttk.Button(
            adv_frame, text="Unlock Advanced Settings", command=self._unlock_advanced
        )
        self.unlock_btn.grid(row=0, column=2, rowspan=2, padx=(20, 0), sticky=tk.N)

        # ── PDF Conversion ─────────────────────────────────────────────
        pdf_frame = ttk.LabelFrame(container, text="PDF Conversion", padding=8)
        pdf_frame.pack(fill=tk.X, pady=(0, 6))

        # Auto-convert toggle
        var_auto = tk.BooleanVar(value=DEFAULTS["auto_convert_pdf"])
        self.vars["auto_convert_pdf"] = var_auto
        ttk.Checkbutton(
            pdf_frame,
            text="Automatically convert to PDF after download completes",
            variable=var_auto,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))

        ttk.Label(pdf_frame, text="Input Dir:").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_pi = tk.StringVar(value=DEFAULTS["pdf_input_dir"])
        self.vars["pdf_input_dir"] = var_pi
        ttk.Entry(pdf_frame, textvariable=var_pi, width=40).grid(
            row=1, column=1, sticky=tk.EW, pady=2
        )
        ttk.Button(
            pdf_frame, text="Browse...", command=lambda: self._browse_dir(var_pi)
        ).grid(row=1, column=2, sticky=tk.W, padx=(4, 0), pady=2)

        ttk.Label(pdf_frame, text="Output Dir:").grid(
            row=2, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_po = tk.StringVar(value=DEFAULTS["pdf_output_dir"])
        self.vars["pdf_output_dir"] = var_po
        ttk.Entry(pdf_frame, textvariable=var_po, width=40).grid(
            row=2, column=1, sticky=tk.EW, pady=2
        )
        ttk.Button(
            pdf_frame, text="Browse...", command=lambda: self._browse_dir(var_po)
        ).grid(row=2, column=2, sticky=tk.W, padx=(4, 0), pady=2)

        ttk.Label(pdf_frame, text="Workers:").grid(
            row=3, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        var_w = tk.IntVar(value=DEFAULTS["pdf_workers"])
        self.vars["pdf_workers"] = var_w
        ttk.Spinbox(pdf_frame, from_=1, to=16, textvariable=var_w, width=6).grid(
            row=3, column=1, sticky=tk.W, pady=2
        )

        pdf_frame.columnconfigure(1, weight=1)

        # ── Action Buttons ─────────────────────────────────────────────
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill=tk.X, pady=(0, 6))

        self.start_btn = ttk.Button(
            btn_frame, text="Start Scraping", command=self._start_scraping
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.convert_btn = ttk.Button(
            btn_frame, text="Convert HTML to PDF", command=self._start_pdf_conversion
        )
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(
            btn_frame, text="Stop", command=self._stop_process, state="disabled"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(btn_frame, text="Clear Log", command=self._clear_log).pack(
            side=tk.RIGHT
        )

        # ── Progress ───────────────────────────────────────────────────
        prog_frame = ttk.Frame(container)
        prog_frame.pack(fill=tk.X, pady=(0, 4))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            prog_frame, variable=self.progress_var, maximum=100
        )
        self.progress_bar.pack(fill=tk.X, side=tk.TOP)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(prog_frame, textvariable=self.status_var, foreground="gray").pack(
            side=tk.LEFT, pady=(2, 0)
        )

        # ── Log Output ─────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(container, text="Log Output", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame, wrap=tk.WORD, height=14, state="disabled", font=("Courier", 11)
        )
        scrollbar = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _browse_dir(self, var: tk.StringVar):
        path = filedialog.askdirectory(initialdir=var.get() or str(PROJECT_DIR))
        if path:
            var.set(path)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def _append_log(self, text: str):
        """Thread-safe log append."""
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _log(self, text: str):
        """Schedule log append on the main thread."""
        self.root.after(0, self._append_log, text)

    def _set_status(self, text: str):
        self.root.after(0, self.status_var.set, text)

    def _set_progress(self, value: float):
        self.root.after(0, self.progress_var.set, value)

    def _set_running(self, running: bool):
        """Toggle button states based on whether a process is running."""

        def _apply():
            state_normal = "normal" if not running else "disabled"
            state_stop = "normal" if running else "disabled"
            self.start_btn.configure(state=state_normal)
            self.convert_btn.configure(state=state_normal)
            self.stop_btn.configure(state=state_stop)

        self.root.after(0, _apply)

    # ─────────────────────────────────────────────────────────────────────
    # CONCURRENT DOWNLOADS TOGGLE
    # ─────────────────────────────────────────────────────────────────────

    def _toggle_concurrent(self):
        enabled = self.vars["concurrent_enabled"].get()
        self.conc_workers_spin.configure(state="normal" if enabled else "disabled")

    # ─────────────────────────────────────────────────────────────────────
    # ADVANCED SETTINGS
    # ─────────────────────────────────────────────────────────────────────

    def _unlock_advanced(self):
        dialog = PasswordDialog(self.root, title="Unlock Advanced Settings")
        if dialog.result is None:
            return
        if dialog.result == ADVANCED_PASSWORD:
            self.advanced_unlocked = True
            for widget in self.adv_widgets:
                widget.configure(state="normal")
            self.unlock_btn.configure(state="disabled", text="Unlocked")
            self.adv_frame.configure(text="Advanced Settings (unlocked)")
        else:
            messagebox.showerror("Error", "Incorrect password.")

    # ─────────────────────────────────────────────────────────────────────
    # CONFIG PERSISTENCE
    # ─────────────────────────────────────────────────────────────────────

    def _get_config(self) -> dict:
        cfg = {}
        for key, var in self.vars.items():
            cfg[key] = var.get()
        return cfg

    def _save_config(self):
        cfg = self._get_config()
        try:
            with open(GUI_CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            self._log(f"Warning: could not save config: {e}\n")

    def _load_config(self):
        if not GUI_CONFIG_FILE.exists():
            return
        try:
            with open(GUI_CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            for key, value in cfg.items():
                if key in self.vars:
                    self.vars[key].set(value)
            # Restore concurrent toggle state
            self._toggle_concurrent()
        except Exception as e:
            print(f"Warning: could not load config: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # UPDATE http_scraper.py CONFIG BLOCK
    # ─────────────────────────────────────────────────────────────────────

    def _resolve_downloads_dir(self, cfg: dict) -> str:
        """Build the effective downloads directory path from GUI fields."""
        folder_name = cfg["downloads_dir"] or f"downloads_{cfg['village_code']}"
        save_path = cfg.get("save_path", "").strip()
        if save_path:
            return str(Path(save_path) / folder_name)
        return folder_name

    def _patch_main_http_config(self) -> bool:
        """
        Rewrite the CONFIG dict in http_scraper.py to match GUI settings,
        so the subprocess picks up the right values.
        """
        main_path = SRC_DIR / "http_scraper.py"
        if not main_path.exists():
            self._log("ERROR: http_scraper.py not found.\n")
            return False

        cfg = self._get_config()
        downloads_dir = self._resolve_downloads_dir(cfg)

        new_config_block = (
            "CONFIG = {\n"
            f'    "district_code": "{cfg["district_code"]}",\n'
            f'    "tehsil_code": "{cfg["tehsil_code"]}",\n'
            f'    "village_code": "{cfg["village_code"]}",\n'
            f'    "period": "{cfg["period"]}",\n'
            f'    "khewat_start": {cfg["khewat_start"]},\n'
            f'    "khewat_end": {cfg["khewat_end"]},\n'
            f'    "min_delay": {cfg["min_delay"]},\n'
            f'    "max_delay": {cfg["max_delay"]},\n'
            f'    "max_retries": {cfg["max_retries"]},\n'
            f'    "page_load_timeout": {cfg["page_load_timeout"]},\n'
            f'    "form_postback_sleep": {cfg["form_postback_sleep"]},\n'
            f'    "downloads_dir": "{downloads_dir}",\n'
            f'    "progress_file": "{cfg["progress_file"]}",\n'
            "}"
        )

        try:
            text = main_path.read_text()

            # Find and replace the CONFIG block using a regex
            import re

            pattern = r"CONFIG\s*=\s*\{[^}]+\}"
            if not re.search(pattern, text):
                self._log("ERROR: Could not find CONFIG block in http_scraper.py.\n")
                return False
            text = re.sub(pattern, new_config_block, text, count=1)

            main_path.write_text(text)
            self._log(f"Updated CONFIG in http_scraper.py.\n")
            self._log(f"Downloads dir: {downloads_dir}\n")
            return True
        except Exception as e:
            self._log(f"ERROR: Failed to patch http_scraper.py: {e}\n")
            return False

    # ─────────────────────────────────────────────────────────────────────
    # SUBPROCESS MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def _read_output(self, proc: subprocess.Popen, label: str, on_complete=None):
        """Read subprocess stdout/stderr and push to log. Runs in a thread."""
        try:
            for line in proc.stdout:
                self._log(line)
            proc.wait()
        except Exception as e:
            self._log(f"\n[{label}] Stream error: {e}\n")

        code = proc.returncode
        self._log(f"\n[{label}] Process exited with code {code}.\n")
        self._set_status(f"{label} finished (exit {code})")
        self._set_progress(100 if code == 0 else 0)
        self._set_running(False)
        self.process = None

        # Fire callback on the main thread (e.g. auto-convert after scraping)
        if on_complete:
            self.root.after(100, on_complete, code)

    def _launch(self, cmd: list[str], label: str, on_complete=None):
        """Launch a subprocess and wire output to the log area.

        Args:
            cmd: Command to run.
            label: Display label for log messages.
            on_complete: Optional callback(exit_code) called on the main thread
                         after the process finishes.
        """
        self._set_running(True)
        self._set_status(f"Running: {label}...")
        self._set_progress(0)
        self._log(f"$ {' '.join(cmd)}\n\n")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(PROJECT_DIR),
            )
        except Exception as e:
            self._log(f"ERROR launching process: {e}\n")
            self._set_running(False)
            self._set_status("Error")
            return

        self.process = proc
        self.thread = threading.Thread(
            target=self._read_output, args=(proc, label, on_complete), daemon=True
        )
        self.thread.start()

    def _stop_process(self):
        if self.process and self.process.poll() is None:
            self._log("\n--- Sending termination signal ---\n")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log("--- Force killing process ---\n")
                self.process.kill()
            self._set_status("Stopped by user")
            self._set_running(False)
            self.process = None

    # ─────────────────────────────────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────────────────────────────────

    def _start_scraping(self):
        if self.process and self.process.poll() is None:
            messagebox.showwarning(
                "Busy", "A process is already running. Stop it first."
            )
            return

        cfg = self._get_config()
        cookie = cfg["session_cookie"].strip()
        if not cookie:
            messagebox.showerror("Missing Cookie", "Please enter a session cookie.")
            return
        if not cfg["village_code"].strip():
            messagebox.showerror("Missing Village", "Please enter a village code.")
            return

        self._save_config()

        # Patch CONFIG in http_scraper.py
        if not self._patch_main_http_config():
            return

        cmd = [
            sys.executable,
            str(SRC_DIR / "http_scraper.py"),
            "--cookie",
            cookie,
            "--start",
            str(cfg["khewat_start"]),
            "--end",
            str(cfg["khewat_end"]),
        ]

        # Concurrent download workers
        if cfg.get("concurrent_enabled", False):
            workers = cfg.get("concurrent_workers", 3)
            workers = max(3, min(8, workers))
            cmd += ["--workers", str(workers)]
            self._log(f"Concurrent mode: {workers} workers\n")

        # Chain auto-conversion if enabled
        on_done = None
        if cfg.get("auto_convert_pdf", False):
            on_done = self._on_scraping_complete

        self._launch(cmd, "Scraper", on_complete=on_done)

    def _start_pdf_conversion(self, input_dir_override: str = None):
        """Manually or automatically trigger PDF conversion.

        Args:
            input_dir_override: If provided, use this as input dir instead of
                                the GUI field (used by auto-convert).
        """
        if self.process and self.process.poll() is None:
            messagebox.showwarning(
                "Busy", "A process is already running. Stop it first."
            )
            return

        cfg = self._get_config()
        input_dir = input_dir_override or cfg["pdf_input_dir"].strip()
        output_dir = cfg["pdf_output_dir"].strip()

        # Fall back to the scraper downloads directory if input dir is empty
        if not input_dir:
            input_dir = self._resolve_downloads_dir(cfg)

        if not input_dir:
            messagebox.showerror(
                "Missing Input",
                "Please select a PDF input directory or set a downloads directory.",
            )
            return

        self._save_config()

        workers = cfg.get("pdf_workers", 4)

        cmd = [
            sys.executable,
            str(SRC_DIR / "pdf_converter.py"),
            "--input",
            input_dir,
            "--workers",
            str(workers),
            "--skip-existing",
        ]
        if output_dir:
            cmd += ["--output", output_dir]

        self._launch(cmd, "PDF Converter")

    def _on_scraping_complete(self, exit_code: int):
        """Called after scraper finishes when auto-convert is enabled."""
        cfg = self._get_config()
        downloads_dir = self._resolve_downloads_dir(cfg)

        self._log(f"\n--- Auto-converting HTML to PDF from {downloads_dir} ---\n")
        self._start_pdf_conversion(input_dir_override=downloads_dir)

    # ─────────────────────────────────────────────────────────────────────
    # CLEANUP
    # ─────────────────────────────────────────────────────────────────────

    def on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(
                "Confirm", "A process is still running. Quit anyway?"
            ):
                return
            self.process.terminate()
        self._save_config()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = JamabandiGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
