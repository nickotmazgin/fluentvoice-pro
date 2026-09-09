"""FluentVoice Pro - Modern Windows 11 Fluent UI Settings & Control Center
Author: Nick Otmazgin
"""

import sys
import os
import ctypes
import webbrowser
import threading
import subprocess
from pathlib import Path
import customtkinter as ctk

# Ensure package imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
from fluentvoice import config, core

PAYPAL_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=4HM44VH47LSMW"
GITHUB_REPO_URL = "https://github.com/nickotmazgin/fluentvoice-pro"
GITHUB_ISSUES_URL = "https://github.com/nickotmazgin/fluentvoice-pro/issues"
GITHUB_PROFILE_URL = "https://github.com/nickotmazgin"

BASE_VOICE_MAP = {
    # English (US) HD Neural
    "Andrew Multilingual (US HD Male)": "en-US-AndrewMultilingualNeural",
    "Ava Multilingual (US HD Female)": "en-US-AvaMultilingualNeural",
    "Brian Multilingual (US HD Casual)": "en-US-BrianMultilingualNeural",
    "Emma Multilingual (US HD Expressive)": "en-US-EmmaMultilingualNeural",
    "Jenny (US HD Studio Female)": "en-US-JennyNeural",
    "Guy (US HD Studio Male)": "en-US-GuyNeural",
    # English (UK) HD Neural
    "Ryan (UK HD British Male)": "en-GB-RyanNeural",
    "Sonia (UK HD British Female)": "en-GB-SoniaNeural",
    # Hebrew HD Neural
    "Avri (Hebrew HD Male)": "he-IL-AvriNeural",
    "Hila (Hebrew HD Female)": "he-IL-HilaNeural",
    # World Languages HD Neural
    "Alvaro (Spanish HD Spain)": "es-ES-AlvaroNeural",
    "Dalia (Spanish HD Mexico)": "es-MX-DaliaNeural",
    "Henri (French HD France)": "fr-FR-HenriNeural",
    "Conrad (German HD Germany)": "de-DE-ConradNeural",
    "Diego (Italian HD Italy)": "it-IT-DiegoNeural",
    "Hamed (Arabic HD Saudi Arabia)": "ar-SA-HamedNeural",
    "Keita (Japanese HD Japan)": "ja-JP-KeitaNeural",
}

def build_full_voice_map():
    vm = BASE_VOICE_MAP.copy()
    installed = core.get_installed_sapi_voices()
    for label, desc in installed:
        vm[f"{label} (Offline 0ms)"] = desc
    return vm

def focus_existing_settings_window(preferred_tab: str | None = None) -> bool:
    """Checks if an instance of the Settings window is already open and brings it to front.
    Optionally requests a tab switch via pending_tab.txt for the live window to pick up.
    """
    try:
        if preferred_tab:
            pending = config.APP_DIR / "pending_tab.txt"
            pending.write_text(preferred_tab, encoding="utf-8")

        hwnd = ctypes.windll.user32.FindWindowW(None, "FluentVoice Pro - Settings & Control Center")
        if hwnd:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            else:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW

            fore_hwnd = user32.GetForegroundWindow()
            fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
            cur_thread = kernel32.GetCurrentThreadId()
            if fore_thread != cur_thread:
                user32.AttachThreadInput(fore_thread, cur_thread, True)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(fore_thread, cur_thread, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False

class FluentVoiceSettingsWindow(ctk.CTk):
    def __init__(self, initial_tab="Voice & Speech"):
        super().__init__()

        self.title("FluentVoice Pro - Settings & Control Center")
        self.geometry("780x740")
        self.minsize(720, 640)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color="#080C14")

        self._set_window_icon()
        self._enable_windows_dark_titlebar()

        self.cfg = config.load_config()
        self.voice_map = build_full_voice_map()
        self._syncing_from_disk = False

        self._build_header()
        self._build_tabs(initial_tab)
        self._build_footer()
        self.after(400, self._poll_external_updates)

    def _set_window_icon(self):
        try:
            ico = Path(__file__).parent.parent / "assets" / "icon.ico"
            if ico.exists():
                self.iconbitmap(default=str(ico))
        except Exception:
            pass

    def _enable_windows_dark_titlebar(self):
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            val = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))

            caption_color = ctypes.c_uint(0x00140C08)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))

            text_color = ctypes.c_uint(0x00FFFFFF)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
        except Exception:
            pass

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="#101622", corner_radius=12, border_width=1, border_color="#00D2FF")
        header_frame.pack(fill="x", padx=16, pady=(14, 6))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🔊 FluentVoice Pro",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#00D2FF"
        )
        title_lbl.pack(side="left", padx=16, pady=10)

        badge_lbl = ctk.CTkLabel(
            header_frame,
            text="v1.4.3 • Windows 11/10 Suite • By Nick Otmazgin",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#8B949E"
        )
        badge_lbl.pack(side="right", padx=16, pady=10)

    def _build_tabs(self, initial_tab):
        self.tabview = ctk.CTkTabview(
            self,
            fg_color="#121824",
            segmented_button_fg_color="#0D131D",
            segmented_button_selected_color="#00D2FF",
            segmented_button_selected_hover_color="#33DCFF",
            segmented_button_unselected_color="#182234",
            segmented_button_unselected_hover_color="#202D45",
            text_color="#0B0F19"
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=6)

        self.tab_reader = self.tabview.add("Direct Text Reader")
        self.tab_speech = self.tabview.add("Voice & Speech")
        self.tab_options = self.tabview.add("Automation & System")
        self.tab_about = self.tabview.add("About & Developer")

        self._populate_reader_tab()
        self._populate_speech_tab()
        self._populate_options_tab()
        self._populate_about_tab()

        valid_tabs = ["Direct Text Reader", "Voice & Speech", "Automation & System", "About & Developer"]
        if initial_tab in valid_tabs:
            self.tabview.set(initial_tab)

    def _populate_reader_tab(self):
        tab = self.tab_reader

        card = ctk.CTkFrame(tab, fg_color="#182234", corner_radius=10)
        card.pack(fill="both", expand=True, padx=10, pady=6)

        top_bar = ctk.CTkFrame(card, fg_color="transparent")
        top_bar.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            top_bar,
            text="📋 Paste or Type Text Below to Read Aloud:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#E6EDF3"
        ).pack(side="left")

        self.reader_meta_lbl = ctk.CTkLabel(
            top_bar,
            text="0 words • 0 chars • Lang: English/Latin",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E"
        )
        self.reader_meta_lbl.pack(side="right")

        # Active voice awareness row (voice is global, not locked to this tab)
        voice_bar = ctk.CTkFrame(card, fg_color="#101622", corner_radius=8)
        voice_bar.pack(fill="x", padx=14, pady=(0, 6))

        self.reader_voice_lbl = ctk.CTkLabel(
            voice_bar,
            text=self._format_reader_voice_label(),
            font=ctk.CTkFont(size=12),
            text_color="#C9D1D9",
            anchor="w"
        )
        self.reader_voice_lbl.pack(side="left", padx=(12, 8), pady=8, fill="x", expand=True)

        btn_change_voice = ctk.CTkButton(
            voice_bar,
            text="🎙 Change Voice →",
            width=140,
            height=28,
            fg_color="#1F2E45",
            hover_color="#2A3B58",
            border_width=1,
            border_color="#00D2FF",
            text_color="#00D2FF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_reader_goto_voice_tab
        )
        btn_change_voice.pack(side="right", padx=10, pady=6)

        # Multi-line text box
        self.reader_textbox = ctk.CTkTextbox(
            card,
            fg_color="#0D131D",
            text_color="#F0F6FC",
            border_color="#1F2E45",
            border_width=1,
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            wrap="word"
        )
        self.reader_textbox.pack(fill="both", expand=True, padx=14, pady=6)
        self.reader_textbox.bind("<KeyRelease>", self._on_reader_text_change)

        sample_starter = "Paste articles, documents, notes, or OCR text directly into this scratchpad window to read them aloud with natural HD voice synthesis."
        self.reader_textbox.insert("1.0", sample_starter)
        self._update_reader_meta()

        # Action Buttons
        btn_bar = ctk.CTkFrame(card, fg_color="transparent")
        btn_bar.pack(fill="x", padx=14, pady=(6, 8))

        btn_paste = ctk.CTkButton(
            btn_bar,
            text="📋 Paste Clipboard",
            fg_color="#1F2E45",
            hover_color="#2A3B58",
            width=135,
            command=self._on_reader_paste
        )
        btn_paste.pack(side="left", padx=(0, 8))

        btn_clear = ctk.CTkButton(
            btn_bar,
            text="🗑️ Clear",
            fg_color="#1F2E45",
            hover_color="#2A3B58",
            width=90,
            command=self._on_reader_clear
        )
        btn_clear.pack(side="left", padx=(0, 8))

        self.btn_reader_speak = ctk.CTkButton(
            btn_bar,
            text="▶️ Read Aloud",
            fg_color="#00D2FF",
            hover_color="#33DCFF",
            text_color="#080C14",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_reader_speak
        )
        self.btn_reader_speak.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_reader_stop = ctk.CTkButton(
            btn_bar,
            text="⏹️ Stop",
            fg_color="#3B1D28",
            hover_color="#522434",
            border_width=1,
            border_color="#F85149",
            text_color="#FF7B72",
            width=100,
            command=self._on_reader_stop
        )
        self.btn_reader_stop.pack(side="right")

        # Live status
        self.reader_status_lbl = ctk.CTkLabel(
            card,
            text="Ready • Paste or type text and click Read Aloud",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E"
        )
        self.reader_status_lbl.pack(anchor="w", padx=14, pady=(0, 8))

    def _format_reader_voice_label(self) -> str:
        curr_voice = self.cfg.get("voice", "en-US-AndrewMultilingualNeural")
        label = curr_voice
        for l, code in self.voice_map.items():
            if code == curr_voice or code.lower() in curr_voice.lower() or curr_voice.lower() in code.lower():
                label = l
                break
        auto = " • Smart auto-route ON" if self.cfg.get("auto_route_language", True) else ""
        return f"🎙 Active reading voice: {label}{auto}"

    def _refresh_reader_voice_label(self):
        if hasattr(self, "reader_voice_lbl"):
            self.reader_voice_lbl.configure(text=self._format_reader_voice_label())

    def _on_reader_goto_voice_tab(self):
        self.tabview.set("Voice & Speech")
        if hasattr(self, "test_status_lbl"):
            self.test_status_lbl.configure(
                text="Pick any voice below — it applies to Direct Text Reader, tray, and auto-read.",
                text_color="#00D2FF"
            )

    def _on_reader_text_change(self, event=None):
        self._update_reader_meta()

    def _update_reader_meta(self):
        txt = self.reader_textbox.get("1.0", "end-1c").strip()
        words = len(txt.split()) if txt else 0
        chars = len(txt)
        detected = core.detect_language(txt)
        lang_names = {
            "hebrew": "Hebrew 🇮🇱",
            "arabic": "Arabic 🇸🇦",
            "cjk": "Japanese/CJK 🇯🇵",
            "cyrillic": "Cyrillic 🌐",
            "latin": "English/Latin 🌐"
        }
        lang_str = lang_names.get(detected, "Universal 🌐")
        self.reader_meta_lbl.configure(text=f"{words:,} words • {chars:,} chars • Lang: {lang_str}")
        self._refresh_reader_voice_label()

    def _on_reader_paste(self):
        clip = core.get_clipboard_text()
        if clip:
            self.reader_textbox.delete("1.0", "end")
            self.reader_textbox.insert("1.0", clip)
            self._update_reader_meta()
            self.reader_status_lbl.configure(text=f"Pasted {len(clip):,} characters from clipboard", text_color="#00D2FF")

    def _on_reader_clear(self):
        self.reader_textbox.delete("1.0", "end")
        self._update_reader_meta()
        self.reader_status_lbl.configure(text="Text cleared", text_color="#8B949E")

    def _on_reader_speak(self):
        txt = self.reader_textbox.get("1.0", "end-1c").strip()
        if not txt:
            self.reader_status_lbl.configure(text="⚠️ Please type or paste text to read aloud", text_color="#F85149")
            return

        self.reader_status_lbl.configure(text="⏳ Synthesizing voice... Connecting to neural engine...", text_color="#00D2FF")

        def run_reader_speech():
            res = core.speak_text(txt)

            def update_status():
                if isinstance(res, dict):
                    if res.get("status") == "success":
                        self.reader_status_lbl.configure(text="✔️ Speech playback active (Zero Collisions)", text_color="#3FB950")
                    elif res.get("status") == "fallback":
                        self.reader_status_lbl.configure(text="ℹ️ Cloud unavailable -> Fallback to Windows offline voice", text_color="#E3B341")
                    elif res.get("status") == "error":
                        self.reader_status_lbl.configure(text="⚠️ " + res.get("message", "Error"), text_color="#F85149")
                    elif res.get("status") == "aborted":
                        self.reader_status_lbl.configure(text="⏹️ Speech superseded / stopped", text_color="#8B949E")
                else:
                    self.reader_status_lbl.configure(text="✔️ Speech synthesis completed", text_color="#3FB950")

            self.after(0, update_status)

        threading.Thread(target=run_reader_speech, daemon=True).start()

    def _on_reader_stop(self):
        core.stop_all_playback()
        self.reader_status_lbl.configure(text="⏹️ Speech stopped immediately", text_color="#8B949E")

    def _populate_speech_tab(self):
        tab = self.tab_speech

        scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color="transparent",
            scrollbar_button_color="#30363D",
            scrollbar_button_hover_color="#00D2FF",
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Voice selection card
        voice_card = ctk.CTkFrame(scroll, fg_color="#182234", corner_radius=10)
        voice_card.pack(fill="x", padx=10, pady=(8, 5))

        header_row = ctk.CTkFrame(voice_card, fg_color="transparent")
        header_row.pack(fill="x", padx=14, pady=(8, 4))

        ctk.CTkLabel(
            header_row,
            text="Active Voice Profile (English, Hebrew, World & Offline):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3"
        ).pack(side="left")

        self.btn_offline = ctk.CTkButton(
            header_row,
            text="➕ Offline Voices (Windows Settings)",
            width=230,
            height=26,
            fg_color="transparent",
            hover_color="#202D45",
            border_width=1,
            border_color="#00D2FF",
            text_color="#00D2FF",
            font=ctk.CTkFont(size=11),
            command=self._on_open_windows_speech_settings
        )
        self.btn_offline.pack(side="right")

        curr_voice = self.cfg.get("voice", "en-US-AndrewMultilingualNeural")
        curr_label = "Andrew Multilingual (US HD Male)"
        for l, code in self.voice_map.items():
            if code == curr_voice or code.lower() in curr_voice.lower() or curr_voice.lower() in code.lower():
                curr_label = l
                break

        self.voice_var = ctk.StringVar(value=curr_label)
        # Fixed width so the dropdown list matches the control (avoids full-bleed bar + tiny list mismatch).
        self.voice_menu = ctk.CTkOptionMenu(
            voice_card,
            values=list(self.voice_map.keys()),
            variable=self.voice_var,
            command=self._on_voice_changed,
            width=480,
            height=36,
            corner_radius=8,
            fg_color="#1F2E45",
            button_color="#00D2FF",
            button_hover_color="#33DCFF",
            text_color="#E6EDF3",
            dropdown_fg_color="#121824",
            dropdown_hover_color="#00D2FF",
            dropdown_text_color="#E6EDF3",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        self.voice_menu.pack(anchor="w", padx=14, pady=(0, 4))

        self.offline_status_lbl = ctk.CTkLabel(
            voice_card,
            text="Tip: Voice choice applies everywhere — Direct Text Reader, tray, and Auto-Read.",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E"
        )
        self.offline_status_lbl.pack(anchor="w", padx=14, pady=(0, 10))

        # Modulation card
        mod_card = ctk.CTkFrame(scroll, fg_color="#182234", corner_radius=10)
        mod_card.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            mod_card,
            text="Speech Modulation",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00D2FF"
        ).pack(anchor="w", padx=14, pady=(10, 2))

        # Rate slider
        rate_box = ctk.CTkFrame(mod_card, fg_color="transparent")
        rate_box.pack(fill="x", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            rate_box,
            text="Speech Speed / Pace:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3"
        ).pack(side="left")

        curr_rate = self.cfg.get("rate_mult", 1.0)
        self.rate_val_lbl = ctk.CTkLabel(
            rate_box,
            text=f"{curr_rate:.1f}x",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00D2FF"
        )
        self.rate_val_lbl.pack(side="right")

        self.rate_slider = ctk.CTkSlider(
            mod_card,
            from_=0.5,
            to=2.0,
            number_of_steps=15,
            command=self._on_rate_slider,
            progress_color="#00D2FF",
            button_color="#00D2FF",
            button_hover_color="#33DCFF"
        )
        self.rate_slider.set(curr_rate)
        self.rate_slider.pack(fill="x", padx=14, pady=(2, 8))

        # Pitch slider
        pitch_box = ctk.CTkFrame(mod_card, fg_color="transparent")
        pitch_box.pack(fill="x", padx=14, pady=(4, 2))

        ctk.CTkLabel(
            pitch_box,
            text="Voice Pitch / Tone Modulation:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3"
        ).pack(side="left")

        curr_pitch = self.cfg.get("pitch_hz", 0)
        pitch_txt = f"{curr_pitch:+d}Hz (Default)" if curr_pitch == 0 else f"{curr_pitch:+d}Hz"
        self.pitch_val_lbl = ctk.CTkLabel(
            pitch_box,
            text=pitch_txt,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00D2FF"
        )
        self.pitch_val_lbl.pack(side="right")

        self.pitch_slider = ctk.CTkSlider(
            mod_card,
            from_=-40,
            to=40,
            number_of_steps=16,
            command=self._on_pitch_slider,
            progress_color="#00D2FF",
            button_color="#00D2FF",
            button_hover_color="#33DCFF"
        )
        self.pitch_slider.set(curr_pitch)
        self.pitch_slider.pack(fill="x", padx=14, pady=(2, 6))

        # Volume slider
        vol_box = ctk.CTkFrame(mod_card, fg_color="transparent")
        vol_box.pack(fill="x", padx=14, pady=(4, 2))

        ctk.CTkLabel(
            vol_box,
            text="Playback Volume:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3"
        ).pack(side="left")

        curr_vol = int(self.cfg.get("volume", 100))
        self.vol_val_lbl = ctk.CTkLabel(
            vol_box,
            text=f"{curr_vol}%",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00D2FF"
        )
        self.vol_val_lbl.pack(side="right")

        self.vol_slider = ctk.CTkSlider(
            mod_card,
            from_=10,
            to=100,
            number_of_steps=18,
            command=self._on_volume_slider,
            progress_color="#00D2FF",
            button_color="#00D2FF",
            button_hover_color="#33DCFF"
        )
        self.vol_slider.set(curr_vol)
        self.vol_slider.pack(fill="x", padx=14, pady=(2, 6))

        # Reset button
        btn_reset = ctk.CTkButton(
            mod_card,
            text="↺ Reset Speed, Pitch & Volume (1.0x, +0Hz, 100%)",
            fg_color="#182234",
            hover_color="#202D45",
            border_width=1,
            border_color="#8B949E",
            text_color="#8B949E",
            height=26,
            font=ctk.CTkFont(size=11),
            command=self._on_reset_speech_modulation
        )
        btn_reset.pack(anchor="w", padx=14, pady=(2, 10))

        # Test card
        test_card = ctk.CTkFrame(scroll, fg_color="#182234", corner_radius=10)
        test_card.pack(fill="x", padx=10, pady=(5, 10))

        ctk.CTkLabel(
            test_card,
            text="Preview & Test Voice:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3"
        ).pack(anchor="w", padx=14, pady=(8, 4))

        self.test_entry = ctk.CTkEntry(
            test_card,
            placeholder_text="Enter custom text to preview voice...",
            font=ctk.CTkFont(size=13),
            border_color="#00D2FF",
            fg_color="#0D131D"
        )
        self.test_entry.pack(fill="x", padx=14, pady=(2, 8))
        self.test_entry.insert(0, "Welcome to FluentVoice Pro! High-definition natural speech synthesis is active.")

        btn_row = ctk.CTkFrame(test_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 6))

        self.btn_speak = ctk.CTkButton(
            btn_row,
            text="▶   Speak Test Text",
            fg_color="#00D2FF",
            hover_color="#33DCFF",
            text_color="#080C14",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_test_speak
        )
        self.btn_speak.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            btn_row,
            text="⏹ Stop Speech",
            fg_color="#21262D",
            hover_color="#30363D",
            font=ctk.CTkFont(size=13),
            command=self._on_test_stop
        )
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=(6, 0))

        self.test_status_lbl = ctk.CTkLabel(
            test_card,
            text="Ready • Click Speak Test Text to preview voice",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E"
        )
        self.test_status_lbl.pack(anchor="w", padx=14, pady=(2, 10))

    def _section_card(self, parent, title: str):
        """Consistent dark section card with cyan title for Settings tabs."""
        card = ctk.CTkFrame(parent, fg_color="#182234", corner_radius=10)
        card.pack(fill="x", padx=10, pady=(4, 6))
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00D2FF"
        ).pack(anchor="w", padx=14, pady=(10, 4))
        return card

    def _populate_options_tab(self):
        tab = self.tab_options

        scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color="transparent",
            scrollbar_button_color="#30363D",
            scrollbar_button_hover_color="#00D2FF",
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # --- Clipboard / Auto-Read ---
        clip = self._section_card(scroll, "Clipboard & Auto-Read")
        self.switch_autoread = ctk.CTkSwitch(
            clip,
            text="Auto-Read on Copy (speak clipboard after stability buffer)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_autoread
        )
        if self.cfg.get("auto_read_copy", False):
            self.switch_autoread.select()
        self.switch_autoread.pack(anchor="w", padx=16, pady=(4, 6))

        buffer_frame = ctk.CTkFrame(clip, fg_color="transparent")
        buffer_frame.pack(fill="x", padx=16, pady=(0, 2))
        ctk.CTkLabel(
            buffer_frame,
            text="Stability buffer (pause after copy):",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E"
        ).pack(side="left")
        curr_buf = self.cfg.get("debounce_sec", 0.6)
        self.buf_val_lbl = ctk.CTkLabel(
            buffer_frame,
            text=f"{curr_buf:.1f}s",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00D2FF"
        )
        self.buf_val_lbl.pack(side="right")
        self.buf_slider = ctk.CTkSlider(
            clip,
            from_=0.3,
            to=1.5,
            number_of_steps=12,
            command=self._on_buffer_slider,
            progress_color="#00D2FF",
            button_color="#00D2FF",
            button_hover_color="#33DCFF"
        )
        self.buf_slider.set(curr_buf)
        self.buf_slider.pack(fill="x", padx=16, pady=(0, 12))

        # --- Language & cleaning ---
        lang = self._section_card(scroll, "Language & Text Cleaning")
        self.switch_autoroute = ctk.CTkSwitch(
            lang,
            text="Smart Language Auto-Routing (Hebrew, Arabic, Spanish, French, ...)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_autoroute
        )
        if self.cfg.get("auto_route_language", True):
            self.switch_autoroute.select()
        self.switch_autoroute.pack(anchor="w", padx=16, pady=(4, 6))

        self.switch_markdown = ctk.CTkSwitch(
            lang,
            text="AI Markdown & PDF Cleaner (code blocks, URLs, OCR line breaks)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_markdown
        )
        if self.cfg.get("clean_markdown", True):
            self.switch_markdown.select()
        self.switch_markdown.pack(anchor="w", padx=16, pady=(0, 6))

        self.switch_notify = ctk.CTkSwitch(
            lang,
            text="Windows Notifications & Toasts",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_notifications
        )
        if self.cfg.get("show_notifications", True):
            self.switch_notify.select()
        self.switch_notify.pack(anchor="w", padx=16, pady=(0, 12))

        # --- Hotkey ---
        hk = self._section_card(scroll, "Global Hotkey")
        self.switch_hotkey = ctk.CTkSwitch(
            hk,
            text="Enable hotkey (toggle Speak / Stop from any app)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_hotkey
        )
        if self.cfg.get("hotkey_enabled", True):
            self.switch_hotkey.select()
        self.switch_hotkey.pack(anchor="w", padx=16, pady=(4, 4))

        hk_row = ctk.CTkFrame(hk, fg_color="transparent")
        hk_row.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(
            hk_row,
            text="Chord:",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E"
        ).pack(side="left")
        self.hotkey_entry = ctk.CTkEntry(
            hk_row,
            width=200,
            font=ctk.CTkFont(size=12),
            border_color="#00D2FF",
            fg_color="#0D131D"
        )
        self.hotkey_entry.pack(side="left", padx=(10, 8))
        self.hotkey_entry.insert(0, self.cfg.get("hotkey", "ctrl+shift+space"))
        self.hotkey_entry.bind("<FocusOut>", lambda e: self._on_hotkey_commit())
        self.hotkey_entry.bind("<Return>", lambda e: self._on_hotkey_commit())
        ctk.CTkButton(
            hk_row,
            text="Apply",
            width=70,
            height=28,
            fg_color="#21262D",
            hover_color="#30363D",
            command=self._on_hotkey_commit
        ).pack(side="left")
        ctk.CTkLabel(
            hk,
            text="Default: ctrl+shift+space  |  Win+Shift+S is reserved by Snipping Tool",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # --- Preferred voices ---
        pref = self._section_card(scroll, "Preferred Voices (Auto-Route)")
        ctk.CTkLabel(
            pref,
            text="When a language is detected, use this voice instead of the active profile:",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E"
        ).pack(anchor="w", padx=16, pady=(0, 6))

        self._pref_combos = {}
        pref_choices = {
            "hebrew": [("Avri (Hebrew HD Male)", "he-IL-AvriNeural"), ("Hila (Hebrew HD Female)", "he-IL-HilaNeural")],
            "english": [
                ("Andrew Multilingual", "en-US-AndrewMultilingualNeural"),
                ("Ava Multilingual", "en-US-AvaMultilingualNeural"),
                ("Jenny (Studio)", "en-US-JennyNeural"),
                ("Guy (Studio)", "en-US-GuyNeural"),
            ],
            "spanish": [("Alvaro (Spain)", "es-ES-AlvaroNeural"), ("Dalia (Mexico)", "es-MX-DaliaNeural")],
            "french": [("Henri (France)", "fr-FR-HenriNeural")],
            "german": [("Conrad (Germany)", "de-DE-ConradNeural")],
            "italian": [("Diego (Italy)", "it-IT-DiegoNeural")],
            "arabic": [("Hamed (Saudi)", "ar-SA-HamedNeural")],
            "cjk": [("Keita (Japanese)", "ja-JP-KeitaNeural")],
        }
        labels = {
            "hebrew": "Hebrew",
            "english": "English",
            "spanish": "Spanish",
            "french": "French",
            "german": "German",
            "italian": "Italian",
            "arabic": "Arabic",
            "cjk": "Japanese / CJK",
        }
        prefs = self.cfg.get("preferred_voices") or {}
        for lang_key, options in pref_choices.items():
            row = ctk.CTkFrame(pref, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(
                row,
                text=f"{labels[lang_key]}:",
                width=110,
                anchor="w",
                font=ctk.CTkFont(size=12),
                text_color="#C9D1D9"
            ).pack(side="left")
            display_names = [o[0] for o in options]
            code_by_name = {o[0]: o[1] for o in options}
            name_by_code = {o[1]: o[0] for o in options}
            combo = ctk.CTkComboBox(
                row,
                values=display_names,
                width=280,
                height=28,
                font=ctk.CTkFont(size=12),
                dropdown_font=ctk.CTkFont(size=12),
                fg_color="#0D131D",
                border_color="#30363D",
                button_color="#00D2FF",
                button_hover_color="#33DCFF",
                dropdown_fg_color="#121824",
                dropdown_hover_color="#00D2FF",
                command=lambda choice, k=lang_key, m=code_by_name: self._on_pref_voice(k, m.get(choice, ""))
            )
            current_code = prefs.get(lang_key, options[0][1])
            combo.set(name_by_code.get(current_code, options[0][0]))
            combo.pack(side="left", padx=(4, 0))
            self._pref_combos[lang_key] = combo
        ctk.CTkLabel(
            pref,
            text="Tip: Avri vs Hila, Alvaro vs Dalia — auto-route uses your pick.",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E"
        ).pack(anchor="w", padx=16, pady=(6, 12))

        # --- Tray daemon ---
        tray = self._section_card(scroll, "System Tray Daemon")
        self.tray_status_lbl = ctk.CTkLabel(
            tray,
            text="Checking tray…",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E"
        )
        self.tray_status_lbl.pack(anchor="w", padx=16, pady=(2, 6))
        tray_btns = ctk.CTkFrame(tray, fg_color="transparent")
        tray_btns.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(
            tray_btns,
            text="Ensure Tray Running",
            width=160,
            height=30,
            fg_color="#00D2FF",
            hover_color="#33DCFF",
            text_color="#080C14",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_ensure_tray
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            tray_btns,
            text="Restart Tray",
            width=120,
            height=30,
            fg_color="#21262D",
            hover_color="#30363D",
            command=self._on_restart_tray
        ).pack(side="left")
        self.after(200, self._refresh_tray_status)

        # --- Tips ---
        tips = self._section_card(scroll, "How to Trigger FluentVoice")
        guide = (
            "• Direct Text Reader — paste/type long text, then Read Aloud.\n"
            "• Tray icon — left-click toggles speak/stop; right-click for voices and settings.\n"
            "• Global hotkey — Ctrl+Shift+Space (configurable above).\n"
            "• Desktop shortcut — opens Control Center and revives tray if needed.\n"
            "• Close to Tray — hides Settings and ensures the tray icon is running.\n"
            "• Explorer — right-click desktop/folder background → FluentVoice Pro (Read Aloud)."
        )
        ctk.CTkLabel(
            tips,
            text=guide,
            font=ctk.CTkFont(size=12),
            text_color="#C9D1D9",
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _populate_about_tab(self):
        tab = self.tab_about

        card = ctk.CTkFrame(tab, fg_color="#182234", corner_radius=10)
        card.pack(fill="both", expand=True, padx=10, pady=8)

        ctk.CTkLabel(
            card,
            text="Maintainer & Lead Developer:",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#E6EDF3"
        ).pack(anchor="w", padx=16, pady=(12, 2))

        ctk.CTkLabel(
            card,
            text="Nick Otmazgin (@nickotmazgin)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#00D2FF"
        ).pack(anchor="w", padx=16, pady=(0, 2))

        bio = "Systems Administrator • Linux Kernel & GNOME Developer • Windows 11 & Win32 Systems Developer • Israel"
        ctk.CTkLabel(card, text=bio, font=ctk.CTkFont(size=12), text_color="#8B949E").pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            card,
            text="Featured Open-Source Projects:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3"
        ).pack(anchor="w", padx=16, pady=(4, 2))

        projects = (
            "• FluentVoice Pro — Native Windows 11 Text-to-Speech & Background Voice Suite\n"
            "• ClipFlow Pro — Advanced Clipboard Synchronization Daemon\n"
            "• Linux Desktop Infrastructure & Kernel Performance Tooling"
        )
        ctk.CTkLabel(card, text=projects, font=ctk.CTkFont(size=12), text_color="#C9D1D9", justify="left").pack(anchor="w", padx=16, pady=(0, 10))

        # Links & Actions
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=4)

        btn_donate = ctk.CTkButton(
            btn_frame,
            text="💖 Donate (PayPal)",
            fg_color="#00D2FF",
            hover_color="#33DCFF",
            text_color="#080C14",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: webbrowser.open(PAYPAL_DONATE_URL)
        )
        btn_donate.pack(side="left", padx=(0, 8))

        btn_repo = ctk.CTkButton(
            btn_frame,
            text="🌐 GitHub Repo",
            fg_color="#21262D",
            hover_color="#30363D",
            command=lambda: webbrowser.open(GITHUB_REPO_URL)
        )
        btn_repo.pack(side="left", padx=(0, 8))

        btn_bug = ctk.CTkButton(
            btn_frame,
            text="🐛 Report Bug / Feedback",
            fg_color="#21262D",
            hover_color="#30363D",
            command=lambda: webbrowser.open(GITHUB_ISSUES_URL)
        )
        btn_bug.pack(side="left")

        ctk.CTkLabel(
            card,
            text="Licensed under the MIT License • Built with Python, Win32 API & CustomTkinter.",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E"
        ).pack(anchor="w", padx=16, pady=(12, 8))

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(4, 14))

        status_lbl = ctk.CTkLabel(
            footer,
            text="Single-Stream Engine Active • Zero Collisions",
            text_color="#3FB950",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        status_lbl.pack(side="left")

        self.autosave_lbl = ctk.CTkLabel(
            footer,
            text="✓ All settings auto-saved",
            text_color="#8B949E",
            font=ctk.CTkFont(size=12)
        )
        self.autosave_lbl.pack(side="left", padx=(16, 0))

        btn_close = ctk.CTkButton(
            footer,
            text="Close to Tray",
            fg_color="#21262D",
            hover_color="#30363D",
            width=110,
            command=self._on_close_to_tray
        )
        btn_close.pack(side="right")

    def _on_close_to_tray(self):
        """Hide Settings and ensure the tray daemon is alive (fixes Exit → reopen → no tray)."""
        try:
            from .lifecycle import ensure_tray_running
            ok = ensure_tray_running(wait_sec=1.2)
            if hasattr(self, "autosave_lbl"):
                if ok:
                    self.autosave_lbl.configure(text="✓ Tray running — closing…", text_color="#3FB950")
                else:
                    self.autosave_lbl.configure(text="⚠ Could not start tray — check install", text_color="#F85149")
        except Exception:
            pass
        self.after(150, self.destroy)

    def _poll_external_updates(self):
        """Live-sync tray/CLI changes into the open Settings window (tabs + toggles + voice)."""
        try:
            pending = config.APP_DIR / "pending_tab.txt"
            if pending.exists():
                tab = pending.read_text(encoding="utf-8").strip()
                pending.unlink(missing_ok=True)
                valid = ["Direct Text Reader", "Voice & Speech", "Automation & System", "About & Developer"]
                if tab in valid:
                    self.tabview.set(tab)
                    self.lift()
                    self.focus_force()
        except Exception:
            pass

        try:
            fresh = config.load_config()
            changed = False

            def apply_switch(attr, key, default=False):
                nonlocal changed
                if not hasattr(self, attr):
                    return
                switch = getattr(self, attr)
                want = bool(fresh.get(key, default))
                have = switch.get() == 1
                if want != have:
                    self._syncing_from_disk = True
                    try:
                        if want:
                            switch.select()
                        else:
                            switch.deselect()
                    finally:
                        self._syncing_from_disk = False
                    changed = True

            apply_switch("switch_autoread", "auto_read_copy", False)
            apply_switch("switch_autoroute", "auto_route_language", True)
            apply_switch("switch_markdown", "clean_markdown", True)
            apply_switch("switch_notify", "show_notifications", True)

            # Debounce slider
            if hasattr(self, "buf_slider"):
                want_buf = float(fresh.get("debounce_sec", self.cfg.get("debounce_sec", 0.6)))
                have_buf = round(float(self.cfg.get("debounce_sec", 0.6)), 1)
                if round(want_buf, 1) != have_buf:
                    self._syncing_from_disk = True
                    try:
                        self.buf_slider.set(want_buf)
                        self.buf_val_lbl.configure(text=f"{want_buf:.1f}s")
                    finally:
                        self._syncing_from_disk = False
                    changed = True

            # Voice selection from tray
            if hasattr(self, "voice_menu"):
                want_voice = fresh.get("voice", self.cfg.get("voice"))
                if want_voice != self.cfg.get("voice"):
                    label = want_voice
                    for l, code in self.voice_map.items():
                        if code == want_voice or code.lower() in want_voice.lower() or want_voice.lower() in code.lower():
                            label = l
                            break
                    self._syncing_from_disk = True
                    try:
                        self.voice_var.set(label)
                        self.voice_menu.set(label)
                    finally:
                        self._syncing_from_disk = False
                    changed = True

            # Rate / pitch from other instances (rare but keep coherent)
            if hasattr(self, "rate_slider"):
                want_rate = float(fresh.get("rate_mult", self.cfg.get("rate_mult", 1.0)))
                if round(want_rate, 1) != round(float(self.cfg.get("rate_mult", 1.0)), 1):
                    self._syncing_from_disk = True
                    try:
                        self.rate_slider.set(want_rate)
                        self.rate_val_lbl.configure(text=f"{want_rate:.1f}x")
                    finally:
                        self._syncing_from_disk = False
                    changed = True
            if hasattr(self, "pitch_slider"):
                want_pitch = int(fresh.get("pitch_hz", self.cfg.get("pitch_hz", 0)))
                if want_pitch != int(self.cfg.get("pitch_hz", 0)):
                    self._syncing_from_disk = True
                    try:
                        self.pitch_slider.set(want_pitch)
                        txt = f"{want_pitch:+d}Hz (Default)" if want_pitch == 0 else f"{want_pitch:+d}Hz"
                        self.pitch_val_lbl.configure(text=txt)
                    finally:
                        self._syncing_from_disk = False
                    changed = True
            if hasattr(self, "vol_slider"):
                want_vol = int(fresh.get("volume", self.cfg.get("volume", 100)))
                if want_vol != int(self.cfg.get("volume", 100)):
                    self._syncing_from_disk = True
                    try:
                        self.vol_slider.set(want_vol)
                        self.vol_val_lbl.configure(text=f"{want_vol}%")
                    finally:
                        self._syncing_from_disk = False
                    changed = True

            self.cfg = fresh
            if changed:
                self._refresh_reader_voice_label()
                self.autosave_lbl.configure(text="✓ Synced from tray / live config", text_color="#00D2FF")
                self.after(1600, lambda: self.autosave_lbl.configure(text="✓ All settings auto-saved", text_color="#8B949E"))
        except Exception:
            pass

        self.after(500, self._poll_external_updates)

    def _trigger_autosave_indicator(self):
        self.autosave_lbl.configure(text="✓ Settings Saved", text_color="#00D2FF")
        self.after(1600, lambda: self.autosave_lbl.configure(text="✓ All settings auto-saved", text_color="#8B949E"))

    def _on_voice_changed(self, choice):
        if self._syncing_from_disk:
            return
        vcode = self.voice_map.get(choice, "en-US-AndrewMultilingualNeural")
        self.cfg["voice"] = vcode
        if "sapi" in vcode.lower() or "desktop" in vcode.lower():
            self.cfg["engine"] = "offline"
        else:
            self.cfg["engine"] = "neural"
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()
        self._refresh_reader_voice_label()
        core.trigger_notification("FluentVoice Pro", f"🗣️ Voice selected: {choice}")
        self.test_status_lbl.configure(text=f"Selected voice: {choice}", text_color="#00D2FF")

    def _on_open_windows_speech_settings(self):
        # Immediate UI feedback — os.system("start ...") blocks and feels stuck.
        if hasattr(self, "offline_status_lbl"):
            self.offline_status_lbl.configure(
                text="Opening Windows Speech Settings… (add language packs / offline voices there)",
                text_color="#00D2FF"
            )
        if hasattr(self, "btn_offline"):
            self.btn_offline.configure(state="disabled", text="Opening…")

        def open_settings():
            try:
                os.startfile("ms-settings:speech")
            except Exception:
                try:
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", "ms-settings:speech"],
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                except Exception:
                    pass

            def restore_btn():
                if hasattr(self, "btn_offline"):
                    self.btn_offline.configure(state="normal", text="➕ Offline Voices (Windows Settings)")
                if hasattr(self, "offline_status_lbl"):
                    self.offline_status_lbl.configure(
                        text="Windows Speech Settings opened. Install voices, then re-open FluentVoice if needed.",
                        text_color="#3FB950"
                    )

            self.after(0, restore_btn)

        threading.Thread(target=open_settings, daemon=True).start()

    def _on_rate_slider(self, val):
        if self._syncing_from_disk:
            return
        self.rate_val_lbl.configure(text=f"{val:.1f}x")
        self.cfg["rate_mult"] = round(val, 1)
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_pitch_slider(self, val):
        if self._syncing_from_disk:
            return
        pitch_int = int(round(val))
        txt = f"{pitch_int:+d}Hz (Default)" if pitch_int == 0 else f"{pitch_int:+d}Hz"
        self.pitch_val_lbl.configure(text=txt)
        self.cfg["pitch_hz"] = pitch_int
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_volume_slider(self, val):
        if self._syncing_from_disk:
            return
        vol = int(round(val))
        self.vol_val_lbl.configure(text=f"{vol}%")
        self.cfg["volume"] = vol
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_reset_speech_modulation(self):
        self.rate_slider.set(1.0)
        self.rate_val_lbl.configure(text="1.0x")
        self.pitch_slider.set(0)
        self.pitch_val_lbl.configure(text="+0Hz (Default)")
        if hasattr(self, "vol_slider"):
            self.vol_slider.set(100)
            self.vol_val_lbl.configure(text="100%")
        self.cfg["rate_mult"] = 1.0
        self.cfg["pitch_hz"] = 0
        self.cfg["volume"] = 100
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()
        self.test_status_lbl.configure(text="Speed, pitch & volume reset (1.0x, +0Hz, 100%)", text_color="#8B949E")

    def _on_toggle_hotkey(self):
        if self._syncing_from_disk:
            return
        self.cfg["hotkey_enabled"] = self.switch_hotkey.get() == 1
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_hotkey_commit(self):
        if self._syncing_from_disk:
            return
        raw = (self.hotkey_entry.get() or "").strip().lower().replace(" ", "")
        if not raw:
            raw = "ctrl+shift+space"
            self.hotkey_entry.delete(0, "end")
            self.hotkey_entry.insert(0, raw)
        # Normalize separators
        raw = raw.replace("++", "+")
        self.cfg["hotkey"] = raw
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_pref_voice(self, lang_key: str, voice_code: str):
        if self._syncing_from_disk or not voice_code:
            return
        prefs = dict(self.cfg.get("preferred_voices") or {})
        prefs[lang_key] = voice_code
        self.cfg["preferred_voices"] = prefs
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _refresh_tray_status(self):
        try:
            from .lifecycle import is_tray_running
            running = is_tray_running()
            if hasattr(self, "tray_status_lbl"):
                if running:
                    self.tray_status_lbl.configure(
                        text="● Tray daemon is running (icon should appear near the clock)",
                        text_color="#3FB950"
                    )
                else:
                    self.tray_status_lbl.configure(
                        text="○ Tray is not running — use Ensure Tray or Close to Tray to revive it",
                        text_color="#F85149"
                    )
        except Exception:
            pass
        self.after(2000, self._refresh_tray_status)

    def _on_ensure_tray(self):
        from .lifecycle import ensure_tray_running
        ok = ensure_tray_running(wait_sec=1.5)
        self._refresh_tray_status()
        if ok:
            self.autosave_lbl.configure(text="✓ Tray started / already running", text_color="#3FB950")
            core.trigger_notification("FluentVoice Pro", "Tray daemon is active")
        else:
            self.autosave_lbl.configure(text="⚠ Failed to start tray", text_color="#F85149")

    def _on_restart_tray(self):
        """Ask running tray to exit, then start a fresh daemon."""
        from .lifecycle import ensure_tray_running, is_tray_running
        flag = config.APP_DIR / "pending_tray_restart.txt"
        try:
            flag.write_text("1", encoding="utf-8")
        except Exception:
            pass
        self.autosave_lbl.configure(text="↻ Restarting tray…", text_color="#00D2FF")

        def wait_and_start():
            import time
            # Wait for old tray to notice flag and exit
            for _ in range(25):
                if not is_tray_running():
                    break
                time.sleep(0.15)
            time.sleep(0.25)
            ok = ensure_tray_running(wait_sec=1.5)

            def done():
                self._refresh_tray_status()
                if ok:
                    self.autosave_lbl.configure(text="✓ Tray restarted", text_color="#3FB950")
                else:
                    self.autosave_lbl.configure(text="⚠ Tray restart failed", text_color="#F85149")

            self.after(0, done)

        threading.Thread(target=wait_and_start, daemon=True).start()

    def _on_toggle_autoread(self):
        if self._syncing_from_disk:
            return
        enabled = self.switch_autoread.get() == 1
        self.cfg["auto_read_copy"] = enabled
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()
        state_str = "Enabled" if enabled else "Disabled"
        core.trigger_notification("FluentVoice Pro", f"⚡ Auto-Read on Copy: {state_str}")

    def _on_buffer_slider(self, val):
        if self._syncing_from_disk:
            return
        buf = round(val, 1)
        self.buf_val_lbl.configure(text=f"{buf:.1f}s")
        self.cfg["debounce_sec"] = buf
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_toggle_autoroute(self):
        if self._syncing_from_disk:
            return
        self.cfg["auto_route_language"] = self.switch_autoroute.get() == 1
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()
        self._refresh_reader_voice_label()

    def _on_toggle_markdown(self):
        if self._syncing_from_disk:
            return
        self.cfg["clean_markdown"] = self.switch_markdown.get() == 1
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_toggle_notifications(self):
        if self._syncing_from_disk:
            return
        self.cfg["show_notifications"] = self.switch_notify.get() == 1
        config.save_config(self.cfg)
        self._trigger_autosave_indicator()

    def _on_test_speak(self):
        txt = self.test_entry.get().strip()
        if not txt:
            txt = "Testing voice synthesis with FluentVoice Pro."

        self.test_status_lbl.configure(text="⏳ Synthesizing voice... Connecting to neural engine...", text_color="#00D2FF")

        def run_test():
            res = core.speak_text(txt)

            def update_status():
                if isinstance(res, dict):
                    if res.get("status") == "success":
                        self.test_status_lbl.configure(text="✔️ Speech playback active (Zero Collisions)", text_color="#3FB950")
                    elif res.get("status") == "fallback":
                        self.test_status_lbl.configure(text="ℹ️ Cloud unavailable -> Fallback to Windows offline voice", text_color="#E3B341")
                    elif res.get("status") == "error":
                        self.test_status_lbl.configure(text="⚠️ Synthesis failed: " + res.get("message", "Error"), text_color="#F85149")
                    elif res.get("status") == "aborted":
                        self.test_status_lbl.configure(text="⏹️ Speech superseded / stopped", text_color="#8B949E")
                else:
                    self.test_status_lbl.configure(text="✔️ Speech synthesis completed", text_color="#3FB950")

            self.after(0, update_status)

        threading.Thread(target=run_test, daemon=True).start()

    def _on_test_stop(self):
        core.stop_all_playback()
        self.test_status_lbl.configure(text="⏹️ Speech stopped immediately", text_color="#8B949E")

def open_settings_window(tab="Voice & Speech"):
    if focus_existing_settings_window(preferred_tab=tab):
        return
    app = FluentVoiceSettingsWindow(initial_tab=tab)
    app.mainloop()

if __name__ == "__main__":
    initial_tab = sys.argv[1] if len(sys.argv) > 1 else "Voice & Speech"
    open_settings_window(tab=initial_tab)
