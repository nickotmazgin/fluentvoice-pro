"""FluentVoice Pro - Modern Windows 11 Fluent UI Settings & Control Center
Author: Nick Otmazgin
"""

import sys
import os
import ctypes
import webbrowser
import threading
from pathlib import Path
import customtkinter as ctk

# Ensure package imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
from fluentvoice import config, core

PAYPAL_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=4HM44VH47LSMW"
GITHUB_REPO_URL = "https://github.com/nickotmazgin/fluentvoice-pro"
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

class FluentVoiceSettingsWindow(ctk.CTk):
    def __init__(self, initial_tab="Voice & Speech"):
        super().__init__()

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title("FluentVoice Pro - Settings & Control Center")
        self.geometry("740x620")
        self.minsize(680, 560)

        self.eval('tk::PlaceWindow . center')

        assets_dir = Path(__file__).parent.parent / "assets"
        ico_path = assets_dir / "icon.ico"
        if not ico_path.exists():
            ico_path = Path.home() / ".antigravity" / "tts_speaker.ico"
        if ico_path.exists():
            try:
                self.iconbitmap(str(ico_path))
            except Exception:
                pass

        self._apply_dark_titlebar()

        self.cfg = config.load_config()
        self.voice_map = build_full_voice_map()

        self._build_header()
        self._build_tabs(initial_tab)
        self._build_footer()

    def _apply_dark_titlebar(self):
        """Forces Windows 11 dark slate caption and removes bright green accent."""
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            
            dark_mode = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))

            caption_color = ctypes.c_uint(0x00221610)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))

            text_color = ctypes.c_uint(0x00FFFFFF)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
        except Exception:
            pass

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="#101622", corner_radius=12, border_width=1, border_color="#00D2FF")
        header_frame.pack(fill="x", padx=16, pady=(16, 8))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🔊 FluentVoice Pro",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#00D2FF"
        )
        title_lbl.pack(side="left", padx=16, pady=10)

        badge_lbl = ctk.CTkLabel(
            header_frame,
            text="v1.3.0 • Windows 11/10 Suite • By Nick Otmazgin",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#8B949E"
        )
        badge_lbl.pack(side="right", padx=16, pady=10)

    def _build_tabs(self, initial_tab):
        self.tabview = ctk.CTkTabview(
            self,
            fg_color="#141B28",
            segmented_button_selected_color="#00D2FF",
            segmented_button_selected_hover_color="#00B4DC"
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=8)

        self.tab_speech = self.tabview.add("Voice & Speech")
        self.tab_options = self.tabview.add("Automation & System")
        self.tab_about = self.tabview.add("About & Developer")

        self._populate_speech_tab()
        self._populate_options_tab()
        self._populate_about_tab()

        if initial_tab in ["Voice & Speech", "Automation & System", "About & Developer"]:
            self.tabview.set(initial_tab)

    def _populate_speech_tab(self):
        tab = self.tab_speech

        # Voice selection card
        voice_card = ctk.CTkFrame(tab, fg_color="#182234", corner_radius=10)
        voice_card.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            voice_card,
            text="Active Voice Profile (English, Hebrew, World Languages & Local Offline):",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#E6EDF3"
        ).pack(anchor="w", padx=14, pady=(8, 4))

        curr_voice = self.cfg.get("voice", "en-US-AndrewMultilingualNeural")
        
        # Match current label
        curr_label = "Andrew Multilingual (US HD Male)"
        for l, code in self.voice_map.items():
            if code == curr_voice or code.lower() in curr_voice.lower() or curr_voice.lower() in code.lower():
                curr_label = l
                break

        self.voice_var = ctk.StringVar(value=curr_label)
        self.voice_menu = ctk.CTkOptionMenu(
            voice_card,
            values=list(self.voice_map.keys()),
            variable=self.voice_var,
            command=self._on_voice_changed,
            fg_color="#00D2FF",
            button_color="#00B4DC",
            text_color="#0B0F19",
            font=ctk.CTkFont(size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(size=13)
        )
        self.voice_menu.pack(fill="x", padx=14, pady=(0, 6))

        # Helper button to install more offline voices via Windows Settings
        btn_offline_help = ctk.CTkButton(
            voice_card,
            text="➕ Add / Download More Offline Voices (Windows Settings)...",
            fg_color="#21262D",
            hover_color="#30363D",
            text_color="#58A6FF",
            font=ctk.CTkFont(size=12),
            height=28,
            command=self._on_open_windows_speech_settings
        )
        btn_offline_help.pack(anchor="w", padx=14, pady=(0, 8))

        # Speed / Rate slider card
        rate_card = ctk.CTkFrame(tab, fg_color="#182234", corner_radius=10)
        rate_card.pack(fill="x", padx=10, pady=6)

        rate_header = ctk.CTkFrame(rate_card, fg_color="transparent")
        rate_header.pack(fill="x", padx=14, pady=(6, 2))
        ctk.CTkLabel(rate_header, text="Speech Speed / Pace:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#E6EDF3").pack(side="left")
        
        curr_mult = self.cfg.get("rate_mult", 1.0)
        self.rate_val_lbl = ctk.CTkLabel(rate_header, text=f"{curr_mult:.1f}x", text_color="#00D2FF", font=ctk.CTkFont(weight="bold"))
        self.rate_val_lbl.pack(side="right")

        self.rate_slider = ctk.CTkSlider(
            rate_card,
            from_=0.6,
            to=1.6,
            number_of_steps=10,
            command=self._on_rate_slider,
            progress_color="#00D2FF",
            button_color="#00D2FF"
        )
        self.rate_slider.set(curr_mult)
        self.rate_slider.pack(fill="x", padx=14, pady=(2, 10))

        # Live Test Card
        test_card = ctk.CTkFrame(tab, fg_color="#182234", corner_radius=10)
        test_card.pack(fill="both", expand=True, padx=10, pady=6)

        ctk.CTkLabel(test_card, text="Preview & Test Voice:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#E6EDF3").pack(anchor="w", padx=14, pady=(6, 4))

        self.test_entry = ctk.CTkEntry(
            test_card,
            placeholder_text="Type or paste any text to test voice synthesis...",
            font=ctk.CTkFont(size=13),
            border_color="#00D2FF"
        )
        self.test_entry.insert(0, "Hello Nick! FluentVoice Pro is active with single-stream collision locking.")
        self.test_entry.pack(fill="x", padx=14, pady=(0, 8))

        btn_row = ctk.CTkFrame(test_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 8))

        self.btn_test = ctk.CTkButton(
            btn_row,
            text="▶️ Speak Test Text",
            fg_color="#00D2FF",
            hover_color="#00B4DC",
            text_color="#0B0F19",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_test_speak
        )
        self.btn_test.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            btn_row,
            text="⏹️ Stop Speech",
            fg_color="#30363D",
            hover_color="#DA3633",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=core.stop_all_playback
        )
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=(6, 0))

    def _populate_options_tab(self):
        tab = self.tab_options

        card = ctk.CTkFrame(tab, fg_color="#182234", corner_radius=10)
        card.pack(fill="both", expand=True, padx=10, pady=8)

        # Switch 1: Auto-Read on copy
        self.switch_autoread = ctk.CTkSwitch(
            card,
            text="Auto-Read on Copy (Reads clipboard text automatically after 0.8s stability buffer)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_autoread
        )
        if self.cfg.get("auto_read_copy", False):
            self.switch_autoread.select()
        self.switch_autoread.pack(anchor="w", padx=16, pady=12)

        # Switch 2: AI & Markdown formatting cleaner
        self.switch_markdown = ctk.CTkSwitch(
            card,
            text="AI Markdown Cleaner (Strips code blocks, backticks, URLs, and asterisks for natural reading)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_markdown
        )
        if self.cfg.get("clean_markdown", True):
            self.switch_markdown.select()
        self.switch_markdown.pack(anchor="w", padx=16, pady=12)

        # Switch 3: Windows Notifications & Toasts
        self.switch_notify = ctk.CTkSwitch(
            card,
            text="Show Windows Notifications & Toasts (Alerts for voice changes, auto-read toggle, and speech events)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_notifications
        )
        if self.cfg.get("show_notifications", True):
            self.switch_notify.select()
        self.switch_notify.pack(anchor="w", padx=16, pady=12)

        # Information box
        info_box = ctk.CTkFrame(card, fg_color="#101622", corner_radius=8)
        info_box.pack(fill="x", padx=16, pady=(10, 12))

        ctk.CTkLabel(
            info_box,
            text="⚡ How to Trigger FluentVoice Pro Anywhere in Windows:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00D2FF"
        ).pack(anchor="w", padx=12, pady=(8, 4))

        guide = (
            "• 1-Click System Tray: Left-click the cyan speaker icon next to the clock.\n"
            "• Single Desktop Shortcut: Double-click 'FluentVoice Pro' to open Control Center.\n"
            "• Windows Explorer: Right-click any folder or desktop background -> 'FluentVoice Pro (Read Aloud)'.\n"
            "• Instant Toggle: Clicking while audio is playing immediately halts playback."
        )
        ctk.CTkLabel(info_box, text=guide, font=ctk.CTkFont(size=12), text_color="#C9D1D9", justify="left").pack(anchor="w", padx=12, pady=(0, 8))

    def _populate_about_tab(self):
        tab = self.tab_about

        card = ctk.CTkFrame(tab, fg_color="#182234", corner_radius=10)
        card.pack(fill="both", expand=True, padx=10, pady=8)

        ctk.CTkLabel(
            card,
            text="Project Lead & Author: Nick Otmazgin",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#00D2FF"
        ).pack(anchor="w", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            card,
            text="Systems Administrator • Linux Kernel & GNOME Developer • Israel\nDeveloper Email: nickotmazgin.dev@gmail.com",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E",
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        repos_frame = ctk.CTkFrame(card, fg_color="#101622", corner_radius=8)
        repos_frame.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            repos_frame,
            text="Other Open-Source Projects by Nick Otmazgin:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3"
        ).pack(anchor="w", padx=12, pady=(8, 2))

        proj_desc = (
            "• ClipFlow Pro — Advanced privacy-safe clipboard manager for GNOME Shell 45–50\n"
            "• Comfort Control (EaseHub) — GNOME Shell panel utilities and system management\n"
            "• Numeric Clock — 24-hour precision DD/MM/YYYY top-bar date & clock"
        )
        ctk.CTkLabel(repos_frame, text=proj_desc, font=ctk.CTkFont(size=12), text_color="#C9D1D9", justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        btn_box = ctk.CTkFrame(card, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(14, 10))

        btn_donate = ctk.CTkButton(
            btn_box,
            text="💖 Donate / Support via PayPal",
            fg_color="#0070BA",
            hover_color="#005EA6",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: webbrowser.open(PAYPAL_DONATE_URL)
        )
        btn_donate.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_repo = ctk.CTkButton(
            btn_box,
            text="🌐 GitHub Repository",
            fg_color="#21262D",
            hover_color="#30363D",
            text_color="#58A6FF",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: webbrowser.open(GITHUB_REPO_URL)
        )
        btn_repo.pack(side="right", fill="x", expand=True, padx=(6, 0))

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

        btn_close = ctk.CTkButton(
            footer,
            text="Close to Tray",
            fg_color="#21262D",
            hover_color="#30363D",
            width=110,
            command=self.destroy
        )
        btn_close.pack(side="right")

    def _on_voice_changed(self, choice):
        vcode = self.voice_map.get(choice, "en-US-AndrewMultilingualNeural")
        self.cfg["voice"] = vcode
        if "sapi" in vcode.lower() or "desktop" in vcode.lower():
            self.cfg["engine"] = "offline"
        else:
            self.cfg["engine"] = "neural"
        config.save_config(self.cfg)
        core.trigger_notification("FluentVoice Pro", f"🗣️ Voice selected: {choice}")

    def _on_open_windows_speech_settings(self):
        os.system("start ms-settings:speech")

    def _on_rate_slider(self, val):
        self.rate_val_lbl.configure(text=f"{val:.1f}x")
        self.cfg["rate_mult"] = round(val, 1)
        config.save_config(self.cfg)

    def _on_toggle_autoread(self):
        enabled = self.switch_autoread.get() == 1
        self.cfg["auto_read_copy"] = enabled
        config.save_config(self.cfg)
        state_str = "Enabled" if enabled else "Disabled"
        core.trigger_notification("FluentVoice Pro", f"⚡ Auto-Read on Copy: {state_str}")

    def _on_toggle_markdown(self):
        self.cfg["clean_markdown"] = self.switch_markdown.get() == 1
        config.save_config(self.cfg)

    def _on_toggle_notifications(self):
        self.cfg["show_notifications"] = self.switch_notify.get() == 1
        config.save_config(self.cfg)

    def _on_test_speak(self):
        txt = self.test_entry.get().strip()
        if not txt:
            txt = "Testing voice synthesis with FluentVoice Pro."
        threading.Thread(target=lambda: core.speak_text(txt), daemon=True).start()

def open_settings_window(tab="Voice & Speech"):
    app = FluentVoiceSettingsWindow(initial_tab=tab)
    app.mainloop()

if __name__ == "__main__":
    open_settings_window()
