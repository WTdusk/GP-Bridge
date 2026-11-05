#!/usr/bin/env python3
"""Modern desktop front-end for GP Bridge. Developer: WTdusk."""
from __future__ import annotations

import json
import sys
import re
import threading
import ctypes
import os
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ai_profile import extract_profile
from gpbridge import convert, parse_gpx, track_names_from_config, write_midi
from preset_manager import COMMUNITY_PRESET_URL, data_dir, default_export_dir, default_preset_dir, list_presets, load_preset, validate_preset

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

BG = "#09080e"; PANEL = "#15131d"; PANEL_2 = "#1d1928"; TEXT = "#f8f7fb"
MUTED = "#a6a1b5"; ACCENT = "#e8a4cb"; LINE = "#302a3d"; GREEN = "#9de4bd"

STRINGS = {
    "en": {
        "workspace":"Workspace", "profiles":"Profiles", "reports":"Reports", "help":"?  Help", "create_profile":"＋  Create profile",
        "hero_title":"From score to sound.", "hero_subtitle":"Write in Guitar Pro. Let your Kontakt instrument perform it.",
        "import_title":"01  Import your score", "import_subtitle":"Drop a Guitar Pro file here, or browse from disk.", "drop_title":"Drop .gpx, .gpif or MusicXML", "drop_hint":"Guitar Pro XML/GPX or MusicXML", "choose_file":"Choose file", "no_score":"No score selected", "score_ready":"Score ready",
        "instrument_title":"02  Choose your instrument", "instrument_subtitle":"Profiles define Keyswitches, CC, channels and velocity behavior.", "instrument_label":"INSTRUMENT PROFILE", "profile_dir_label":"PROFILE FOLDER · DEFAULT: SOFTWARE FOLDER / GPBRIDGEDATA / PROFILES", "choose_folder":"Choose folder", "browse":"Browse", "legato_overlap":"Legato overlap (ticks)", "slide_overlap":"Slide overlap (ticks)", "split_tracks":"Split each instrument into string tracks", "auto_sustain":"Let notes ring until the next note on that string", "strict":"Stop when a technique is unmapped", "profile_empty":"No profiles installed. Get one from the community repository or create your own.", "profile_count":"{count} profile(s) available. Mappings are source-backed.",
        "export_title":"03  Export MIDI", "output_label":"EXPORT FOLDER", "output_default":"MIDI files will be saved to: {folder}", "output_file":"MIDI file: {path}", "export":"Export MIDI", "ready":"Ready to translate", "profile_ready":"{count} instrument profile(s) ready", "exported":"Exported {count} MIDI events", "failed":"Export failed", "profile_created":"Instrument profile created",
        "missing_title":"Missing input", "missing_message":"Choose a score, export folder and instrument profile first.", "unmapped_title":"Unmapped techniques", "export_complete":"Export complete", "export_details":"MIDI written to:\n{midi}\n\nReport:\n{report}", "help_title":"GP Bridge", "help_text":"Import a Guitar Pro score, choose a source-backed instrument profile, then export MIDI for your DAW.\n\nDefault application data folder:\n{folder}\n\nUnmapped techniques are blocked in strict mode.",
        "profile_window":"Create instrument profile", "profile_window_title":"Create a profile from the official guide", "profile_window_desc":"Only documented mappings with page references are saved. Failed or uncertain extraction creates no profile.", "pdf":"Official guide PDF", "library":"Library name", "instrument":"Instrument / preset", "model":"AI model", "endpoint":"Responses API endpoint", "api_key":"OpenAI API key", "browse_pdf":"Browse PDF", "privacy":"The PDF is sent to the configured AI endpoint. The key is used for this request only and is not saved.", "waiting":"Waiting for PDF and AI request.", "extracting":"Extracting mappings from the official PDF…", "cancel":"Cancel", "extract_create":"Extract and create", "missing_details":"Select the guide, enter library/instrument names and an API key.", "missing_details_title":"Missing details", "extract_fail":"Extraction failed. No profile was created.\n{reason}", "profile_saved":"Profile created and validated:\n{path}", "help_button":"Help"
    },
    "zh": {
        "workspace":"工作台", "profiles":"音源预设", "reports":"转换报告", "help":"?  帮助", "create_profile":"＋  创建预设",
        "hero_title":"从乐谱，到声音。", "hero_subtitle":"在 Guitar Pro 写谱，让 Kontakt 音源演奏。",
        "import_title":"01  导入乐谱", "import_subtitle":"拖入 Guitar Pro 文件，或从电脑中选择。", "drop_title":"拖放 .gpx、.gpif 或 MusicXML", "drop_hint":"支持 Guitar Pro XML/GPX 或 MusicXML", "choose_file":"选择乐谱", "no_score":"尚未选择乐谱", "score_ready":"乐谱已就绪",
        "instrument_title":"02  选择音源", "instrument_subtitle":"预设定义 Keyswitch、CC、通道和力度处理方式。", "instrument_label":"音源预设", "profile_dir_label":"预设目录 · 默认位于软件目录 / GPBridgeData / Profiles", "choose_folder":"选择文件夹", "browse":"浏览", "legato_overlap":"连奏重叠 (ticks)", "slide_overlap":"滑弦重叠 (ticks)", "split_tracks":"每个乐器内部再按弦分轨", "auto_sustain":"自动延音至同弦下个音（闷音/断奏除外）", "strict":"遇到未映射技法时停止导出", "profile_empty":"尚未安装预设。请从社区预设库下载，或自行创建。", "profile_count":"找到 {count} 个预设，映射包含来源依据。",
        "export_title":"03  导出 MIDI", "output_label":"导出文件夹", "output_default":"MIDI 文件将保存到：{folder}", "output_file":"MIDI 文件：{path}", "export":"导出 MIDI", "ready":"等待转换", "profile_ready":"已加载 {count} 个音源预设", "exported":"已导出 {count} 个 MIDI 事件", "failed":"导出失败", "profile_created":"音源预设已创建",
        "missing_title":"缺少信息", "missing_message":"请先选择乐谱、导出文件夹和音源预设。", "unmapped_title":"存在未映射技法", "export_complete":"导出完成", "export_details":"MIDI 已写入：\n{midi}\n\n报告：\n{report}", "help_title":"GP Bridge 帮助", "help_text":"导入 Guitar Pro 乐谱，选择有来源依据的音源预设，再导出 MIDI 到 DAW。\n\n默认数据目录：\n{folder}\n\n严格模式会阻止未映射技法的导出。",
        "profile_window":"创建音源预设", "profile_window_title":"从官方 Guide 创建预设", "profile_window_desc":"只保存手册明确记载且带页码的映射。提取失败或结果不确定时不会生成预设。", "pdf":"官方 Guide PDF", "library":"音色库名称", "instrument":"乐器 / 预设名称", "model":"AI 模型", "endpoint":"Responses API 地址", "api_key":"OpenAI API Key", "browse_pdf":"选择 PDF", "privacy":"PDF 会发送到所配置的 AI 接口。API Key 仅用于本次请求，不会保存。", "waiting":"等待选择 PDF 并开始提取。", "extracting":"正在从官方 PDF 提取映射…", "cancel":"取消", "extract_create":"提取并创建", "missing_details":"请选择 PDF，填写音色库和乐器名称，并输入 API Key。", "missing_details_title":"信息不完整", "extract_fail":"提取失败，未创建预设。\n{reason}", "profile_saved":"预设已创建并通过校验：\n{path}", "help_button":"帮助"
    }
}


def enable_windows_dpi_awareness():
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try: ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError): pass


class GPBridgeApp:
    def __init__(self, root: tk.Misc):
        self.root = root
        root.title("GP Bridge"); root.geometry("1180x800"); root.minsize(980, 680); root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close_app)
        try:
            icon_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "gpbridge.ico"
            root.iconbitmap(default=str(icon_path))
        except (OSError, tk.TclError): pass
        self.settings_path = data_dir() / "settings.json"
        self.input_path = tk.StringVar(); self.output_dir = tk.StringVar(value=self._load_saved_output_dir())
        self.output_path = tk.StringVar()
        self.legato_overlap = tk.IntVar(value=self._load_legato_overlap())
        self.slide_overlap = tk.IntVar(value=self._load_slide_overlap())
        self.split_tracks = tk.BooleanVar(value=self._load_split_tracks())
        self.auto_sustain = tk.BooleanVar(value=self._load_auto_sustain())
        self.preset_dir = tk.StringVar(value=self._load_saved_preset_dir()); self.preset = tk.StringVar()
        self.language = tk.StringVar(value=self._load_language()); self.language_choice = tk.StringVar(value="English" if self.language.get() == "en" else "中文")
        self.strict = tk.BooleanVar(value=True); self.status = tk.StringVar(value=self.tr("ready"))
        self._preset_paths: list[Path] = []
        default_preset_dir().mkdir(parents=True, exist_ok=True)
        default_export_dir().mkdir(parents=True, exist_ok=True)
        self._configure_styles(); self._build(); self.refresh_presets()
        self.update_output_preview()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("GP.TButton", background=PANEL_2, foreground=TEXT, borderwidth=0, padding=(14, 9), font=("Segoe UI", 10))
        style.map("GP.TButton", background=[("active", "#332a45")], foreground=[("active", TEXT)])
        style.configure("Accent.TButton", background=TEXT, foreground="#121016", borderwidth=0, padding=(18, 11), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", ACCENT)], foreground=[("active", "#121016")])
        style.configure("GP.TEntry", fieldbackground="#100e16", foreground=TEXT, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=9)
        style.configure("GP.TCombobox", fieldbackground="#100e16", background="#100e16", foreground=TEXT, bordercolor=LINE, arrowcolor=ACCENT, padding=8)
        style.map("GP.TCombobox", fieldbackground=[("readonly", "#100e16")], foreground=[("readonly", TEXT)])
        style.configure("GP.TCheckbutton", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.map("GP.TCheckbutton", background=[("active", PANEL)], foreground=[("active", TEXT)])

    def _build(self):
        if hasattr(self, "scroll_frame"): self.scroll_frame.destroy()
        root = self.root; root.columnconfigure(0, weight=1); root.rowconfigure(0, weight=1)
        self.scroll_frame = tk.Frame(root, bg=BG); self.scroll_frame.grid(row=0, column=0, sticky="nsew")
        self.scroll_frame.columnconfigure(0, weight=1); self.scroll_frame.rowconfigure(0, weight=1)
        canvas = tk.Canvas(self.scroll_frame, bg=BG, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.scroll_frame, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns"); canvas.configure(yscrollcommand=scrollbar.set)
        self.shell = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=self.shell, anchor="nw")
        self.shell.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width, height=max(e.height, self.shell.winfo_reqheight())))
        def scroll(event):
            if event.widget.winfo_class() not in {"TCombobox", "TSpinbox", "Entry", "TEntry", "Text"}:
                canvas.yview_scroll(-int(event.delta / 120), "units")
        root.bind("<MouseWheel>", scroll)
        self.shell.columnconfigure(0, weight=1); self.shell.rowconfigure(2, weight=1); self.shell.rowconfigure(3, weight=1)
        self._header(self.shell); self._hero(self.shell)
        main = tk.Frame(self.shell, bg=BG); main.grid(row=2, column=0, sticky="nsew", padx=34, pady=(0, 18)); main.columnconfigure(0, weight=3); main.columnconfigure(1, weight=2); main.rowconfigure(0, weight=1)
        self._drop_card(main).grid(row=0, column=0, sticky="nsew", padx=(0, 10)); self._profile_card(main).grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self._footer(self.shell)
        if self.input_path.get():
            self.file_label.configure(text=Path(self.input_path.get()).name, fg=TEXT); self.drop_label.configure(text=self.tr("score_ready"), fg=GREEN)

    def tr(self, key, **values):
        text = STRINGS[self.language.get()].get(key, key).format(**values)
        if key == "help_text":
            text += "\n\nDeveloper / 开发者: WTdusk"
        return text

    def _load_language(self):
        try: return json.loads(self.settings_path.read_text(encoding="utf-8")).get("language", "zh")
        except (OSError, ValueError, TypeError): return "zh"

    def change_language(self, _event=None):
        self.language.set("en" if self.language_choice.get() == "English" else "zh")
        self._save_settings(); self._build(); self.refresh_presets(); self.update_output_preview()

    def _header(self, root):
        bar = tk.Frame(root, bg=BG); bar.grid(row=0, column=0, sticky="ew", padx=34, pady=(22, 10)); bar.columnconfigure(2, weight=1)
        tk.Label(bar, text="GP", bg=TEXT, fg="#111016", font=("Segoe UI", 10, "bold"), width=3, pady=4).grid(row=0, column=0, padx=(0, 12))
        tk.Label(bar, text="GP Bridge", bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        nav = tk.Frame(bar, bg=PANEL, highlightthickness=1, highlightbackground=LINE); nav.grid(row=0, column=3, padx=20)
        for i, label in enumerate((self.tr("workspace"), self.tr("profiles"), self.tr("reports"))):
            tk.Label(nav, text=label, bg=PANEL_2 if i == 0 else PANEL, fg=TEXT if i == 0 else MUTED, padx=15, pady=7, font=("Segoe UI", 9)).grid(row=0, column=i)
        ttk.Button(bar, text=self.tr("create_profile"), style="GP.TButton", command=self.create_profile_dialog).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(bar, text=self.tr("help"), style="GP.TButton", command=self.show_help).grid(row=0, column=5, padx=(0, 8))
        language = ttk.Combobox(bar, textvariable=self.language_choice, values=("中文", "English"), state="readonly", width=9, style="GP.TCombobox"); language.grid(row=0, column=6); language.bind("<<ComboboxSelected>>", self.change_language)

    def _hero(self, root):
        hero = tk.Frame(root, bg=BG); hero.grid(row=1, column=0, sticky="ew", padx=34, pady=(18, 22))
        tk.Label(hero, text=self.tr("hero_title"), bg=BG, fg=TEXT, font=("Segoe UI", 30, "bold")).pack(anchor="w")
        tk.Label(hero, text=self.tr("hero_subtitle"), bg=BG, fg=MUTED, font=("Segoe UI", 12)).pack(anchor="w", pady=(8, 0))
        tk.Frame(hero, bg=ACCENT, height=2, width=170).pack(anchor="w", pady=(18, 0))

    def _card(self, parent, title, subtitle):
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=LINE, padx=20, pady=18)
        tk.Label(card, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(card, text=subtitle, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 15)); return card

    def _drop_card(self, parent):
        card = self._card(parent, self.tr("import_title"), self.tr("import_subtitle"))
        self.drop = tk.Frame(card, bg="#100e16", highlightthickness=1, highlightbackground="#493a59", cursor="hand2"); self.drop.pack(fill="both", expand=True, pady=(0, 14)); self.drop.bind("<Button-1>", lambda _e: self.choose_input())
        tk.Label(self.drop, text="+", bg="#100e16", fg=ACCENT, font=("Segoe UI", 30)).pack(pady=(38, 4))
        self.drop_label = tk.Label(self.drop, text=self.tr("drop_title"), bg="#100e16", fg=TEXT, font=("Segoe UI", 12, "bold")); self.drop_label.pack()
        tk.Label(self.drop, text=self.tr("drop_hint"), bg="#100e16", fg=MUTED, font=("Segoe UI", 9)).pack(pady=(7, 34))
        if DND_FILES and hasattr(self.drop, "drop_target_register"):
            self.drop.drop_target_register(DND_FILES); self.drop.dnd_bind("<<Drop>>", self.on_drop)
        row = tk.Frame(card, bg=PANEL); row.pack(fill="x"); ttk.Button(row, text=self.tr("choose_file"), style="GP.TButton", command=self.choose_input).pack(side="left")
        self.file_label = tk.Label(row, text=self.tr("no_score"), bg=PANEL, fg=MUTED, font=("Segoe UI", 9)); self.file_label.pack(side="left", padx=12); return card

    def _profile_card(self, parent):
        card = self._card(parent, self.tr("instrument_title"), self.tr("instrument_subtitle"))
        tk.Label(card, text=self.tr("instrument_label"), bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.preset_box = ttk.Combobox(card, textvariable=self.preset, state="readonly", style="GP.TCombobox"); self.preset_box.pack(fill="x", pady=(7, 15))
        tk.Label(card, text=self.tr("profile_dir_label"), bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), wraplength=320, justify="left").pack(anchor="w")
        folder_row = tk.Frame(card, bg=PANEL); folder_row.pack(fill="x", pady=(7, 14)); ttk.Entry(folder_row, textvariable=self.preset_dir, style="GP.TEntry").pack(side="left", fill="x", expand=True); ttk.Button(folder_row, text=self.tr("choose_folder"), style="GP.TButton", command=self.choose_preset_dir).pack(side="left", padx=(7, 0))
        overlap_row = tk.Frame(card, bg=PANEL); overlap_row.pack(fill="x", pady=(0, 12))
        tk.Label(overlap_row, text=self.tr("legato_overlap"), bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        overlap_box = ttk.Spinbox(overlap_row, from_=0, to=100, width=6, textvariable=self.legato_overlap,
                                  command=self._save_settings, style="GP.TEntry")
        overlap_box.pack(side="right"); overlap_box.bind("<FocusOut>", lambda _event: self._save_settings()); overlap_box.bind("<Return>", lambda _event: self._save_settings())
        slide_row = tk.Frame(card, bg=PANEL); slide_row.pack(fill="x", pady=(0, 12))
        tk.Label(slide_row, text=self.tr("slide_overlap"), bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        slide_box = ttk.Spinbox(slide_row, from_=0, to=960, width=6, textvariable=self.slide_overlap,
                                command=self._save_settings, style="GP.TEntry")
        slide_box.pack(side="right"); slide_box.bind("<FocusOut>", lambda _event: self._save_settings()); slide_box.bind("<Return>", lambda _event: self._save_settings())
        ttk.Checkbutton(card, text=self.tr("split_tracks"), variable=self.split_tracks, style="GP.TCheckbutton", command=self._save_settings).pack(anchor="w", pady=(0, 10))
        ttk.Checkbutton(card, text=self.tr("auto_sustain"), variable=self.auto_sustain, style="GP.TCheckbutton", command=self._save_settings).pack(anchor="w", pady=(0, 10))
        ttk.Checkbutton(card, text=self.tr("strict"), variable=self.strict, style="GP.TCheckbutton").pack(anchor="w", pady=(0, 15))
        ttk.Button(card, text="Community presets" if self.language.get() == "en" else "社区预设库", style="GP.TButton", command=lambda: webbrowser.open(COMMUNITY_PRESET_URL)).pack(anchor="w", pady=(0, 6))
        self.profile_hint = tk.Label(card, text="Profiles are read from JSON and never guessed.", bg=PANEL, fg=GREEN, font=("Segoe UI", 9), wraplength=300, justify="left"); self.profile_hint.pack(anchor="w", pady=(8, 0)); return card

    def _footer(self, root):
        footer = tk.Frame(root, bg=BG); footer.grid(row=3, column=0, sticky="nsew", padx=34, pady=(0, 24)); footer.columnconfigure(0, weight=1); footer.rowconfigure(1, weight=1)
        top = tk.Frame(footer, bg=BG); top.grid(row=0, column=0, sticky="ew", pady=(0, 10)); top.columnconfigure(1, weight=1)
        tk.Label(top, text=self.tr("export_title"), bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w"); ttk.Button(top, text=self.tr("export"), style="Accent.TButton", command=self.convert).grid(row=0, column=2, sticky="e")
        out = tk.Frame(footer, bg=PANEL, highlightthickness=1, highlightbackground=LINE, padx=14, pady=10); out.grid(row=1, column=0, sticky="nsew"); out.columnconfigure(1, weight=1)
        tk.Label(out, text=self.tr("output_label"), bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 12)); ttk.Entry(out, textvariable=self.output_dir, style="GP.TEntry").grid(row=0, column=1, sticky="ew"); ttk.Button(out, text=self.tr("choose_folder"), style="GP.TButton", command=self.choose_output).grid(row=0, column=2, padx=(8, 0))
        self.output_preview = tk.Label(out, text=self.tr("output_default", folder=self.output_dir.get()), bg=PANEL, fg=MUTED, font=("Segoe UI", 8)); self.output_preview.grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))
        self.status_label = tk.Label(out, textvariable=self.status, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)); self.status_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def _load_saved_preset_dir(self):
        try:
            folder = Path(json.loads(self.settings_path.read_text(encoding="utf-8")).get("preset_dir", ""))
            if folder.exists(): return str(folder)
        except (OSError, ValueError, TypeError): pass
        return str(default_preset_dir())

    def _load_saved_output_dir(self):
        try:
            folder = Path(json.loads(self.settings_path.read_text(encoding="utf-8")).get("output_dir", ""))
            if folder.exists(): return str(folder)
        except (OSError, ValueError, TypeError): pass
        return str(default_export_dir())

    def _load_legato_overlap(self):
        try:
            value = int(json.loads(self.settings_path.read_text(encoding="utf-8")).get("legato_overlap_ticks", 5))
            return max(0, min(100, value))
        except (OSError, ValueError, TypeError):
            return 5

    def _load_slide_overlap(self):
        try:
            value = int(json.loads(self.settings_path.read_text(encoding="utf-8")).get("slide_overlap_ticks", 120))
            return max(0, min(960, value))
        except (OSError, ValueError, TypeError):
            return 120

    def _load_split_tracks(self):
        try:
            return bool(json.loads(self.settings_path.read_text(encoding="utf-8")).get("split_tracks", True))
        except (OSError, ValueError, TypeError):
            return True

    def _load_auto_sustain(self):
        try:
            return bool(json.loads(self.settings_path.read_text(encoding="utf-8")).get("auto_sustain", True))
        except (OSError, ValueError, TypeError):
            return True

    def _save_settings(self):
        try: self.settings_path.parent.mkdir(parents=True, exist_ok=True); self.settings_path.write_text(json.dumps({"preset_dir": self.preset_dir.get(), "output_dir": self.output_dir.get(), "language": self.language.get(), "legato_overlap_ticks": max(0, min(100, int(self.legato_overlap.get()))), "slide_overlap_ticks": max(0, min(960, int(self.slide_overlap.get()))), "split_tracks": bool(self.split_tracks.get()), "auto_sustain": bool(self.auto_sustain.get())}, indent=2), encoding="utf-8")
        except (OSError, ValueError, TypeError): pass

    def choose_input(self):
        path = filedialog.askopenfilename(filetypes=[("Guitar Pro / MusicXML", "*.gpx *.gp *.gpif *.xml *.musicxml"), ("All files", "*.*")])
        if path: self.set_input(path)

    def set_input(self, path):
        self.input_path.set(path); self.file_label.configure(text=Path(path).name, fg=TEXT); self.drop_label.configure(text="Score ready", fg=GREEN)
        self.update_output_preview()

    def on_drop(self, event):
        raw = event.data.strip().strip("{}"); self.set_input(raw)

    def choose_output(self):
        path = filedialog.askdirectory(initialdir=self.output_dir.get() or str(default_export_dir()))
        if path: self.output_dir.set(path); self._save_settings(); self.update_output_preview()

    def update_output_preview(self):
        if self.input_path.get():
            out = Path(self.output_dir.get()) / f"{Path(self.input_path.get()).stem}.vst.mid"
            self.output_preview.configure(text=self.tr("output_file", path=out))
        else:
            self.output_preview.configure(text=self.tr("output_default", folder=self.output_dir.get()))

    def choose_preset_dir(self):
        path = filedialog.askdirectory()
        if path: self.preset_dir.set(path); self._save_settings(); self.refresh_presets()

    def refresh_presets(self):
        self._preset_paths = list_presets(self.preset_dir.get()); labels = [f"{p.stem}  /  {p.parent.name}" for p in self._preset_paths]; self.preset_box["values"] = labels
        if labels: self.preset_box.current(0); self.profile_hint.configure(text=self.tr("profile_count", count=len(labels)), fg=GREEN)
        else: self.profile_hint.configure(text=self.tr("profile_empty"), fg=ACCENT)
        self.status.set(self.tr("profile_ready", count=len(labels)))

    def show_help(self):
        messagebox.showinfo(self.tr("help_title"), self.tr("help_text", folder=data_dir()))

    def close_app(self):
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel):
                try: child.destroy()
                except tk.TclError: pass
        try:
            self.root.quit()
            self.root.destroy()
        finally:
            sys.exit(0)

    def convert(self):
        if not self.input_path.get() or not self.output_dir.get() or not self._preset_paths or self.preset_box.current() < 0:
            messagebox.showerror(self.tr("missing_title"), self.tr("missing_message")); return
        try:
            profile = load_preset(self._preset_paths[self.preset_box.current()]); profile["legato_overlap_ticks"] = max(0, min(100, int(self.legato_overlap.get()))); profile["slide_overlap_ticks"] = max(0, min(960, int(self.slide_overlap.get()))); profile["split_tracks"] = bool(self.split_tracks.get()); profile["sustain_mode"] = "auto" if self.auto_sustain.get() else "notated"; errors = validate_preset(profile)
            if errors: raise ValueError("Invalid profile:\n" + "\n".join(errors))
            score = parse_gpx(self.input_path.get()); events, report = convert(score, profile); unmapped = [x for x in report["warnings"] if "unmapped technique" in x]
            if self.strict.get() and unmapped: raise ValueError(self.tr("unmapped_title") + ":\n" + "\n".join(unmapped))
            output_path = Path(self.output_dir.get()) / f"{Path(self.input_path.get()).stem}.vst.mid"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_midi(events, output_path, score.tempo, track_names_from_config(profile), bool(profile.get("split_tracks", True))); report_path = output_path.with_suffix(".report.json"); report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.set(self.tr("exported", count=report["events"])); self.status_label.configure(fg=GREEN); messagebox.showinfo(self.tr("export_complete"), self.tr("export_details", midi=output_path, report=report_path))
        except Exception as exc:
            self.status.set(self.tr("failed")); self.status_label.configure(fg=ACCENT); messagebox.showerror(self.tr("failed"), str(exc))

    def create_profile_dialog(self):
        win = tk.Toplevel(self.root); win.title(self.tr("profile_window")); win.geometry("620x620"); win.minsize(560, 560); win.configure(bg=BG); win.transient(self.root)
        body = tk.Frame(win, bg=BG, padx=24, pady=20); body.pack(fill="both", expand=True); body.columnconfigure(1, weight=1)
        tk.Label(body, text=self.tr("profile_window_title"), bg=BG, fg=TEXT, font=("Segoe UI", 17, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(body, text=self.tr("profile_window_desc"), bg=BG, fg=MUTED, wraplength=540, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 18))
        values = {key: tk.StringVar(value=value) for key, value in {"pdf":"", "library":"", "instrument":"", "model":"gpt-4.1", "endpoint":"https://api.openai.com/v1/responses"}.items()}
        secret = tk.StringVar(); labels = [(self.tr("pdf"), "pdf"), (self.tr("library"), "library"), (self.tr("instrument"), "instrument"), (self.tr("model"), "model"), (self.tr("endpoint"), "endpoint")]
        for row, (label, key) in enumerate(labels, start=2):
            tk.Label(body, text=label, bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
            entry = ttk.Entry(body, textvariable=values[key], style="GP.TEntry"); entry.grid(row=row, column=1, sticky="ew", pady=6)
            if key == "pdf":
                ttk.Button(body, text=self.tr("browse_pdf"), style="GP.TButton", command=lambda: values["pdf"].set(filedialog.askopenfilename(parent=win, filetypes=[("PDF guide", "*.pdf")]))).grid(row=row, column=2, padx=(8, 0))
        keyrow = len(labels) + 2
        tk.Label(body, text=self.tr("api_key"), bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(row=keyrow, column=0, sticky="w", pady=6)
        ttk.Entry(body, textvariable=secret, show="•", style="GP.TEntry").grid(row=keyrow, column=1, columnspan=2, sticky="ew", pady=6)
        tk.Label(body, text=self.tr("privacy"), bg=BG, fg=MUTED, wraplength=520, justify="left").grid(row=keyrow+1, column=0, columnspan=3, sticky="w", pady=(8, 14))
        result = tk.StringVar(value=self.tr("waiting"))
        tk.Label(body, textvariable=result, bg=BG, fg=ACCENT, wraplength=530, justify="left").grid(row=keyrow+2, column=0, columnspan=3, sticky="w", pady=(4, 12))
        buttons = tk.Frame(body, bg=BG); buttons.grid(row=keyrow+3, column=0, columnspan=3, sticky="ew"); buttons.columnconfigure(0, weight=1)
        close_button = ttk.Button(buttons, text=self.tr("cancel"), style="GP.TButton", command=win.destroy); close_button.grid(row=0, column=1, padx=(0, 8))
        create_button = ttk.Button(buttons, text=self.tr("extract_create"), style="Accent.TButton"); create_button.grid(row=0, column=2)

        def begin():
            pdf = values["pdf"].get().strip()
            if not pdf or not values["library"].get().strip() or not values["instrument"].get().strip() or not secret.get().strip():
                messagebox.showerror(self.tr("missing_details_title"), self.tr("missing_details"), parent=win); return
            create_button.configure(state="disabled"); result.set(self.tr("extracting"))
            params = {key: var.get().strip() for key, var in values.items()}; api_key = secret.get().strip()
            threading.Thread(target=run_extract, args=(params, api_key), daemon=True).start()

        def run_extract(params, api_key):
            try:
                profile = extract_profile(params["pdf"], api_key, params["model"], params["endpoint"], params["library"], params["instrument"])
                profile["library"] = params["library"]; profile["instrument"] = params["instrument"]
                profile.setdefault("source", {})["document"] = Path(params["pdf"]).name
                profile.setdefault("vendor", "Native Instruments Kontakt")
                slug = re.sub(r"[^a-z0-9]+", "-", params["library"].lower()).strip("-") or "kontakt-profile"
                target = Path(self.preset_dir.get()) / "kontakt" / f"{slug}.json"
                if target.exists(): raise FileExistsError(f"Profile already exists: {target.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                temp_target = target.with_suffix(target.suffix + ".tmp")
                try:
                    temp_target.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
                    temp_target.replace(target)
                finally:
                    if temp_target.exists(): temp_target.unlink()
                win.after(0, lambda: extraction_done(target, None))
            except Exception as exc:
                win.after(0, lambda err=str(exc): extraction_done(None, err))

        def extraction_done(target, error):
            create_button.configure(state="normal")
            if error:
                result.set(self.tr("extract_fail", reason=error))
                return
            secret.set(""); self.refresh_presets(); result.set(self.tr("profile_saved", path=target)); self.status.set(self.tr("profile_created")); self.status_label.configure(fg=GREEN)

        create_button.configure(command=begin)


def main():
    enable_windows_dpi_awareness()
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk(); GPBridgeApp(root); root.mainloop()


if __name__ == "__main__": main()
