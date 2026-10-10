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
import copy

import customtkinter as ctk

# Ensure package imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
from fluentvoice import config, core, hotkeys, localtts, voices
from fluentvoice import __version__ as APP_VERSION



def _is_store_build() -> bool:
    from fluentvoice import msix
    return msix.is_packaged()

class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame that repaints between wheel steps.

    A fast wheel or touchpad sends events faster than Tk repaints. CTk scrolls on every
    event, so the window never gets the idle time it needs to redraw: moved cards leave
    trails and stale strips behind. Here wheel deltas are summed and applied once per
    frame, followed by an immediate repaint."""

    FRAME_MS = 16

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._wheel_delta = 0
        self._wheel_job = None

    def _mouse_wheel_all(self, event):
        if not sys.platform.startswith("win") or self._shift_pressed:
            return super()._mouse_wheel_all(event)
        if not self._check_if_valid_scroll(event.widget):
            return
        self._wheel_delta += event.delta
        if self._wheel_job is None:
            self._wheel_job = self.after(self.FRAME_MS, self._flush_wheel)

    def _flush_wheel(self):
        self._wheel_job = None
        delta, self._wheel_delta = self._wheel_delta, 0
        canvas = self._parent_canvas
        if delta and canvas.yview() != (0.0, 1.0):
            canvas.yview("scroll", -int(delta / 6), "units")
            canvas.update_idletasks()

PAYPAL_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=4HM44VH47LSMW"
GITHUB_REPO_URL = "https://github.com/nickotmazgin/fluentvoice-pro"
GITHUB_ISSUES_URL = "https://github.com/nickotmazgin/fluentvoice-pro/issues"
GITHUB_PROFILE_URL = "https://github.com/nickotmazgin"
VOICE_LICENSES_URL = "https://github.com/nickotmazgin/fluentvoice-pro/blob/main/docs/VOICE_LICENSES.md"
THIRD_PARTY_URL = "https://github.com/nickotmazgin/fluentvoice-pro/blob/main/THIRD_PARTY_NOTICES.md"

# Neural voices come from fluentvoice/voices.py (shared with the tray + auto-route).
BASE_VOICE_MAP = {label: vid for vid, label, _ in voices.CATALOG}

# Tk text boxes always lay text out left-to-right. Right-aligning Hebrew / Arabic is not enough:
# in a line that mixes in English ("…של FluentVoice Pro פעיל…") the word groups end up on the
# wrong sides. Wrapping each right-to-left line in RLE … PDF gives the correct reading order.
# The marks are invisible, stripped before speaking (core.clean_text_for_speech) and from counts.
RLE, PDF = "\u202b", "\u202c"


def bidi_strip(text: str) -> str:
    return (text or "").replace(RLE, "").replace(PDF, "")


def bidi_wrap_lines(text: str) -> str:
    """Every non-empty line wrapped in RLE … PDF (any old marks removed first)."""
    return "\n".join(f"{RLE}{line}{PDF}" if line.strip() else line for line in bidi_strip(text).split("\n"))


def _index_after_plain(text: str, n: int) -> int:
    """Position in `text` just after its n-th character that is not a bidi mark."""
    seen = 0
    for i, ch in enumerate(text):
        if seen == n and ch != RLE:  # inside the marks: after an opening RLE, before a closing PDF
            return i
        if ch not in (RLE, PDF):
            seen += 1
    return len(text)


def build_full_voice_map():
    vm = BASE_VOICE_MAP.copy()
    for v in localtts.installed_voices():
        vm[voices.label_for(v["id"])] = v["id"]
    installed = core.get_installed_sapi_voices()
    for label, desc in installed:
        vm[f"{label} (Offline)"] = desc
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
        from fluentvoice import shortcuts
        shortcuts.apply_app_identity()  # taskbar groups Settings under FluentVoice Pro, not Python
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
        self._cfg_base = copy.deepcopy(self.cfg)
        self.voice_map = build_full_voice_map()
        self._syncing_from_disk = False

        self._build_header()
        self._build_tabs(initial_tab)
        self._build_footer()
        self.after(400, self._poll_external_updates)
        self.after(1500, lambda: self._check_updates_async(force=False))

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
            text="🔊 FluentVoice Pro™",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#00D2FF"
        )
        title_lbl.pack(side="left", padx=16, pady=10)

        badge_lbl = ctk.CTkLabel(
            header_frame,
            text=f"v{APP_VERSION} • Windows 11/10 Suite • By Nick Otmazgin",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#8B949E"
        )
        badge_lbl.pack(side="right", padx=16, pady=10)

        # Hidden until a newer GitHub release is found
        self.update_badge = ctk.CTkButton(
            header_frame,
            text="⬆ Update available",
            width=150,
            height=28,
            fg_color="#1F6F3F",
            hover_color="#238636",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._show_update_popup(self._update_info),
        )
        self._update_info = None

    def _build_tabs(self, initial_tab):
        self.tabview = ctk.CTkTabview(
            self,
            fg_color="#121824",
            segmented_button_fg_color="#0D131D",
            # Deep teal selected pill + light text on ALL tabs (CTk uses one text_color).
            # Bright cyan fill + near-black text made dormant tabs unreadable.
            segmented_button_selected_color="#0E4A5C",
            segmented_button_selected_hover_color="#13607A",
            segmented_button_unselected_color="#1C2536",
            segmented_button_unselected_hover_color="#2A3548",
            text_color="#E6EDF3",
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=6)

        self.tab_reader = self.tabview.add("Direct Text Reader")
        self.tab_speech = self.tabview.add("Voice & Speech")
        self.tab_providers = self.tabview.add("Voice Providers")
        self.tab_options = self.tabview.add("Automation & System")
        self.tab_about = self.tabview.add("About & Developer")

        self._populate_reader_tab()
        self._populate_speech_tab()
        self._populate_providers_tab()
        self._populate_options_tab()
        self._populate_about_tab()
        self._fit_wide_labels()

        self._valid_tabs = [
            "Direct Text Reader",
            "Voice & Speech",
            "Voice Providers",
            "Automation & System",
            "About & Developer",
        ]
        self._pending_initial_tab = (
            initial_tab if initial_tab in self._valid_tabs else "Voice & Speech"
        )
        # IMPORTANT: do NOT call tabview.set() in a rapid loop. CTkTabview.set()
        # schedules _grid_forget_all_tabs(exclude=name) after 100ms; overlapping
        # sets race and leave the final tab unmapped (blank content pane).
        self.tabview.set(self._pending_initial_tab)
        self.bind("<Map>", self._on_window_mapped)
        self.bind("<Configure>", self._on_window_configure)
        # Re-grid after CTk's delayed forget settles
        self.after(160, self._ensure_active_tab_visible)
        self.after(320, self._ensure_active_tab_visible)

    def _on_window_mapped(self, event=None):
        if event is not None and event.widget is not self:
            return
        self.after(160, self._ensure_active_tab_visible)

    def _select_tab(self, name):
        """Switch tabs programmatically and re-grid once CTk's delayed forget settles."""
        if name not in self._valid_tabs:
            return
        self._pending_initial_tab = name
        self.tabview.set(name)
        self.after(160, self._ensure_active_tab_visible)

    def _ensure_active_tab_visible(self):
        """Make sure the selected tab frame is gridded (CTk blank-tab race fix)."""
        try:
            # A programmatic selection is honoured once, then cleared; afterwards the
            # user's own tab click wins. Keeping it forever made every <Map> (maximize,
            # restore, resize) snap the window back to the initial tab.
            wanted = getattr(self, "_pending_initial_tab", None) or self.tabview.get()
            self._pending_initial_tab = None
            tv = self.tabview
            if wanted not in getattr(tv, "_tab_dict", {}):
                return
            tv._current_name = wanted
            try:
                tv._segmented_button.set(wanted)
            except Exception:
                pass
            # Hide others, show wanted — synchronously (no delayed forget race)
            for name, frame in tv._tab_dict.items():
                if name == wanted:
                    continue
                try:
                    frame.grid_forget()
                except Exception:
                    pass
            tv._set_grid_current_tab()
            self.update_idletasks()
            self._refresh_scroll_regions()
        except Exception:
            pass

    def _resync_active_tab(self):
        """Public alias used by capture helpers."""
        self._ensure_active_tab_visible()

    def _refresh_scroll_regions(self):
        try:
            for attr in ("tab_speech", "tab_providers", "tab_options", "tab_about"):
                tab = getattr(self, attr, None)
                if tab is None:
                    continue
                stack = list(tab.winfo_children())
                while stack:
                    w = stack.pop()
                    canvas = getattr(w, "_parent_canvas", None)
                    if canvas is None and w.__class__.__name__ == "Canvas":
                        canvas = w
                    if canvas is not None:
                        try:
                            bbox = canvas.bbox("all")
                            if bbox:
                                canvas.configure(scrollregion=bbox)
                        except Exception:
                            pass
                    try:
                        stack.extend(w.winfo_children())
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_window_configure(self, event=None):
        """Keep scrollable Settings tabs refreshing after maximize / resize."""
        if event is not None and event.widget is not self:
            return
        try:
            self.update_idletasks()
            self._refresh_scroll_regions()
        except Exception:
            pass

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
        # Packed before the label: a long voice line would otherwise push the button out of a
        # normal-size window.
        btn_change_voice.pack(side="right", padx=10, pady=6)

        self.reader_voice_lbl = ctk.CTkLabel(
            voice_bar,
            text=self._format_reader_voice_label(),
            font=ctk.CTkFont(size=12),
            text_color="#C9D1D9",
            anchor="w",
            justify="left",
        )
        self.reader_voice_lbl.pack(side="left", padx=(12, 8), pady=8, fill="x", expand=True)

        def _wrap_voice_line(event):
            width = event.width - btn_change_voice.winfo_width() - 50
            if width > 100:  # wraplength is in unscaled units, event sizes in pixels
                self.reader_voice_lbl.configure(wraplength=width / ctk.ScalingTracker.get_widget_scaling(self))
        voice_bar.bind("<Configure>", _wrap_voice_line, add="+")

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
        # Tk draws the line that holds the text cursor in two pieces, which breaks right-to-left
        # word order on that line; park the cursor at the end when the Reader loses focus.
        self.reader_textbox.bind("<FocusOut>", self._on_reader_focus_out, add="+")

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
            text="🗑 Clear",
            fg_color="#1F2E45",
            hover_color="#2A3B58",
            width=90,
            command=self._on_reader_clear
        )
        btn_clear.pack(side="left", padx=(0, 8))

        self.btn_reader_speak = ctk.CTkButton(
            btn_bar,
            text="▶  Read Aloud",
            fg_color="#00D2FF",
            hover_color="#33DCFF",
            text_color="#080C14",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_reader_speak
        )
        self.btn_reader_speak.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_reader_stop = ctk.CTkButton(
            btn_bar,
            text="⏹ Stop",
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
        curr_voice = config.load_config().get("voice", "en-US-AndrewMultilingualNeural")
        label = self._label_for_voice(curr_voice)
        auto = (" • Smart auto-route ON: other languages use your Preferred Voices"
                if self.cfg.get("auto_route_language", True) else " • Auto-route OFF")
        if self.cfg.get("offline_only"):
            auto += " • 🛡 Offline only: text stays on this PC"
        return f"🎙 Active reading voice: {label}{auto}"

    def _refresh_reader_voice_label(self):
        if hasattr(self, "reader_voice_lbl"):
            self.reader_voice_lbl.configure(text=self._format_reader_voice_label())

    def _on_reader_goto_voice_tab(self):
        self._select_tab("Voice & Speech")
        if hasattr(self, "test_status_lbl"):
            self.test_status_lbl.configure(
                text="Pick a voice below. It is used by the Reader, tray and Auto-Read (other languages follow your Preferred Voices while auto-route is on).",
                text_color="#00D2FF"
            )

    def _on_reader_text_change(self, event=None):
        # Debounced: language detection on multi-KB text on every keystroke caused typing lag.
        job = getattr(self, "_meta_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._meta_job = self.after(350, self._update_reader_meta)

    def _update_reader_meta(self):
        txt = bidi_strip(self.reader_textbox.get("1.0", "end-1c")).strip()
        words = len(txt.split()) if txt else 0
        chars = len(txt)
        detected = core.detect_language(txt)
        lang_str = voices.LANGUAGES.get(detected, "English/Latin")
        # Hebrew / Arabic text reads right-aligned (the text box itself has no RTL layout).
        tb = self.reader_textbox
        tb.tag_config("rtl", justify="right")
        rtl = detected in voices.RTL_FAMILIES
        self._apply_bidi(tb, rtl)
        if rtl:
            tb.tag_add("rtl", "1.0", "end")
        else:
            tb.tag_remove("rtl", "1.0", "end")
        self.reader_meta_lbl.configure(text=f"{words:,} words • {chars:,} chars • Lang: {lang_str}")
        self._refresh_reader_voice_label()

    def _on_reader_focus_out(self, _event=None):
        tb = self.reader_textbox
        try:
            if tb.tag_ranges("rtl"):
                tb.mark_set("insert", "end-1c")
        except Exception:
            pass

    def _apply_bidi(self, tb, rtl: bool):
        """Add (or remove) the right-to-left marks in the Reader, keeping cursor and scroll."""
        content = tb.get("1.0", "end-1c")
        desired = bidi_wrap_lines(content) if rtl else bidi_strip(content)
        if desired == content:
            return
        plain_before_cursor = len(bidi_strip(tb.get("1.0", "insert")))
        top = tb.yview()[0]
        tb.delete("1.0", "end")
        tb.insert("1.0", desired)
        tb.mark_set("insert", f"1.0+{_index_after_plain(desired, plain_before_cursor)}c")
        tb.yview_moveto(top)

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
        txt = bidi_strip(self.reader_textbox.get("1.0", "end-1c")).strip()
        if not txt:
            self.reader_status_lbl.configure(text="⚠ Please type or paste text to read aloud", text_color="#F85149")
            return
        self._start_speech(txt, self.reader_status_lbl, self.btn_reader_speak, "▶  Read Aloud")

    def _on_reader_stop(self):
        core.stop_all_playback()
        self._finish_speech_ui()
        self.reader_status_lbl.configure(text="⏹ Speech stopped immediately", text_color="#8B949E")

    # ------------------------------------------------------------------
    # Live speech status (shared by Direct Text Reader + Voice test box)
    # Worker thread -> queue -> Tk main loop poll. No Tk calls off the UI thread.
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_ms(ms) -> str:
        s = max(0, int(ms or 0) // 1000)
        return f"{s // 60}:{s % 60:02d}"

    def _voice_short_label(self, voice_code: str) -> str:
        for label, code in self.voice_map.items():
            if code == voice_code:
                return label.split(" (")[0]
        return voice_code

    def _start_speech(self, txt, status_lbl, button, idle_text, auto_route=None, voice=None):
        import queue as _queue
        self._finish_speech_ui()  # restore any previous button
        self._speech_token = getattr(self, "_speech_token", 0) + 1
        token = self._speech_token
        self._speech_ui = {
            "token": token, "lbl": status_lbl, "btn": button, "idle": idle_text,
            "queue": _queue.Queue(), "t0": __import__("time").time(), "phase": "synthesizing",
            "voice": "", "parts": 1, "routed": "",
        }
        try:
            button.configure(text="⏳ Working…", state="disabled")
        except Exception:
            pass
        status_lbl.configure(text="⏳ Preparing the voice…", text_color="#00D2FF")

        q = self._speech_ui["queue"]

        def on_status(phase, info):
            q.put((phase, dict(info)))

        def worker():
            try:
                res = core.speak_text(txt, on_status=on_status, auto_route=auto_route, voice=voice)
            except Exception as e:  # never leave the UI spinning
                res = {"status": "error", "message": f"{type(e).__name__}: {e}"}
            q.put(("__result__", res if isinstance(res, dict) else {}))

        threading.Thread(target=worker, name="fv-reader", daemon=True).start()
        self.after(120, self._poll_speech_status, token)

    def _poll_speech_status(self, token):
        ui = getattr(self, "_speech_ui", None)
        if not ui or ui["token"] != token:
            return
        import time as _time
        lbl = ui["lbl"]
        final = None
        while True:
            try:
                phase, info = ui["queue"].get_nowait()
            except Exception:
                break
            if phase == "__result__":
                final = info
                continue
            ui["phase"] = phase
            if phase == "synthesizing":
                ui["voice"] = self._voice_short_label(info.get("voice", ""))
                ui["voice_id"] = info.get("voice", "")
                ui["parts"] = info.get("parts", 1)
                if info.get("routed_from"):
                    lang = voices.LANGUAGES.get(info.get("lang", ""), "other-language")
                    ui["routed"] = f" • auto-routed for {lang} text (your voice: {voices.short_name(info['routed_from'])})"
            elif phase == "speaking":
                ui["voice"] = self._voice_short_label(info.get("voice", "")) or ui["voice"]
                ui["speak_info"] = info
            elif phase == "fallback":
                ui["reason"] = info.get("reason", "")
                if info.get("voice"):
                    ui["fallback_voice"] = core.voice_display_name(info["voice"])
            elif phase in ("done", "aborted", "error"):
                ui["final_info"] = info

        elapsed = _time.time() - ui["t0"]
        phase = ui["phase"]
        if final is not None:
            status = final.get("status")
            if status == "success":
                lbl.configure(text=f"✔ Finished reading • {ui['voice'] or 'voice'} • {self._fmt_ms(elapsed * 1000)}{ui['routed']}", text_color="#3FB950")
            elif status == "fallback":
                how = "an offline HD voice" if final.get("mode") == "offline_hd" else "the Windows offline voice"
                lbl.configure(text="ℹ " + final.get("message", f"First voice unavailable → finished with {how}"),
                              text_color="#E3B341")
            elif status == "aborted":
                lbl.configure(text="⏹ Speech stopped", text_color="#8B949E")
            else:
                lbl.configure(text="⚠ " + str(final.get("message", "Speech failed")), text_color="#F85149")
            self._finish_speech_ui()
            return

        if phase == "synthesizing":
            local = voices.is_local_hd(ui.get("voice_id", ""))
            msg = (f"⏳ Preparing offline HD voice on this PC… {int(elapsed)}s" if local
                   else f"⏳ Connecting to neural engine… {int(elapsed)}s")
            if elapsed > 5 and not local:
                msg += " — slow network? An offline voice takes over if the service doesn't answer."
            lbl.configure(text=msg, text_color="#00D2FF" if elapsed <= 5 else "#E3B341")
        elif phase == "speaking":
            info = ui.get("speak_info", {})
            if info.get("mode") == "offline":
                lbl.configure(text=f"🔊 Speaking (offline Windows voice) • {self._fmt_ms(elapsed * 1000)}", text_color="#3FB950")
            elif info.get("mode") == "offline_hd":
                part = f" • part {info.get('part', 1)}/{info.get('parts', 1)}" if info.get("parts", 1) > 1 else ""
                pos, ln = info.get("pos_ms", 0), info.get("len_ms", 0)
                clock = f"{self._fmt_ms(pos)} / {self._fmt_ms(ln)}" if ln else self._fmt_ms(pos)
                lbl.configure(text=f"🔊 Speaking — {ui['voice']} (offline HD, on this PC){part} • {clock}{ui['routed']}",
                              text_color="#3FB950")
            else:
                part = f" • part {info.get('part', 1)}/{info.get('parts', 1)}" if info.get("parts", 1) > 1 else ""
                pos = info.get("pos_ms", 0)
                ln = info.get("len_ms", 0)
                clock = f"{self._fmt_ms(pos)} / {self._fmt_ms(ln)}" if ln else self._fmt_ms(pos)
                lbl.configure(text=f"🔊 Speaking — {ui['voice']} (HD neural){part} • {clock}{ui['routed']}", text_color="#3FB950")
            try:
                ui["btn"].configure(text="🔊 Speaking…")
            except Exception:
                pass
        elif phase == "fallback":
            nxt = ui.get("fallback_voice") or "an offline voice"
            lbl.configure(text=f"ℹ Voice unavailable → continuing with {nxt}…", text_color="#E3B341")

        self.after(200, self._poll_speech_status, token)

    def _finish_speech_ui(self):
        ui = getattr(self, "_speech_ui", None)
        if not ui:
            return
        try:
            ui["btn"].configure(text=ui["idle"], state="normal")
        except Exception:
            pass
        self._speech_ui = None

    def _populate_speech_tab(self):
        tab = self.tab_speech

        scroll = SmoothScrollableFrame(
            tab,
            fg_color="transparent",
            scrollbar_button_color="#30363D",
            scrollbar_button_hover_color="#00D2FF",
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Voice selection card — clear hierarchy: title → dropdown → one tip → secondary action
        voice_card = ctk.CTkFrame(scroll, fg_color="#182234", corner_radius=10)
        voice_card.pack(fill="x", padx=10, pady=(8, 5))

        ctk.CTkLabel(
            voice_card,
            text="Active Voice Profile",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 6))

        curr_voice = self.cfg.get("voice", "en-US-AndrewMultilingualNeural")
        curr_label = self._label_for_voice(curr_voice, "Andrew Multilingual (US HD Male)")

        # Language ▸ Voice: 12 languages, then only that language's voices (≤22, no scrolling).
        pick_row = ctk.CTkFrame(voice_card, fg_color="transparent")
        pick_row.pack(fill="x", padx=14, pady=(0, 6))
        groups = self._voice_groups()
        curr_group = self._group_of_label(curr_label)
        self.lang_var = ctk.StringVar(value=curr_group)
        self.lang_menu = ctk.CTkOptionMenu(
            pick_row,
            values=list(groups.keys()),
            variable=self.lang_var,
            command=self._on_voice_language_changed,
            width=230,
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
            anchor="w",
        )
        self.lang_menu.pack(side="left", padx=(0, 8))

        self.voice_var = ctk.StringVar(value=curr_label)
        self.voice_menu = ctk.CTkOptionMenu(
            pick_row,
            values=groups.get(curr_group, [curr_label]),
            variable=self.voice_var,
            command=self._on_voice_changed,
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
            anchor="w",
        )
        self.voice_menu.pack(side="left", fill="x", expand=True)

        self.offline_status_lbl = ctk.CTkLabel(
            voice_card,
            text="Used everywhere (Reader, tray, Auto-Read). With Smart Auto-Routing on, text in another "
                 "language is read by that language's Preferred Voice (Automation & System). "
                 "Multilingual voices read English, Spanish, French, German, Italian and Portuguese themselves.",
            font=ctk.CTkFont(size=12),
            text_color="#C9D1D9",
            wraplength=860,
            justify="left",
            anchor="w",
        )
        self.offline_status_lbl.pack(fill="x", padx=14, pady=(0, 8))

        self.btn_offline = ctk.CTkButton(
            voice_card,
            text="Install Windows Offline Voices…",
            width=260,
            height=28,
            fg_color="transparent",
            hover_color="#202D45",
            border_width=1,
            border_color="#00D2FF",
            text_color="#00D2FF",
            font=ctk.CTkFont(size=12),
            command=self._on_open_windows_speech_settings,
            anchor="w",
        )
        self.btn_offline.pack(anchor="w", padx=14, pady=(0, 12))

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
            # Segoe UI has Hebrew and Arabic letters. With CTk's default Roboto, Tk drew every
            # Hebrew/Arabic word separately in a fallback font, left to right, so the words of a
            # right-to-left line came out in reverse order whatever direction marks were used.
            font=ctk.CTkFont(family="Segoe UI", size=13),
            border_color="#00D2FF",
            fg_color="#0D131D"
        )
        self.test_entry.pack(fill="x", padx=14, pady=(2, 8))
        self.test_entry.insert(0, voices.sample_text(self.cfg.get("voice", voices.DEFAULT_VOICE)))
        self._align_test_entry(self.cfg.get("voice", voices.DEFAULT_VOICE))

        btn_row = ctk.CTkFrame(test_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 6))

        self.btn_speak = ctk.CTkButton(
            btn_row,
            text="▶  Speak Test Text",
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

    def _fit_wide_labels(self):
        """Wrap long hint labels to their card's real width.

        They were created with wraplength=860, which CTk scales by the display scaling
        (1075 px at 125%), so in a normal-size window the text ran past the card and was cut
        off on both sides."""
        stack = [self.tab_speech, self.tab_providers, self.tab_options]
        while stack:
            w = stack.pop()
            stack.extend(w.winfo_children())
            if isinstance(w, ctk.CTkLabel) and w.cget("wraplength") == 860:
                self._wrap_to_parent(w)

    @staticmethod
    def _wrap_to_parent(label, pad: int = 44):
        last = {"w": None}

        def on_configure(event):
            want = max(240, int(event.width / label._get_widget_scaling()) - pad)
            if last["w"] is None or abs(want - last["w"]) > 4:
                last["w"] = want
                label.configure(wraplength=want)

        label.master.bind("<Configure>", on_configure, add="+")

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

        scroll = SmoothScrollableFrame(
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
            text="Smart Language Auto-Routing (reads each language with its Preferred Voice below)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_autoroute
        )
        if self.cfg.get("auto_route_language", True):
            self.switch_autoroute.select()
        self.switch_autoroute.pack(anchor="w", padx=16, pady=(4, 6))

        self.switch_markdown = ctk.CTkSwitch(
            lang,
            text="Markdown & PDF Text Cleaner (code blocks, URLs, OCR line breaks)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_markdown
        )
        if self.cfg.get("clean_markdown", True):
            self.switch_markdown.select()
        self.switch_markdown.pack(anchor="w", padx=16, pady=(0, 12))


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
            width=72,
            anchor="w",
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

        stop_row = ctk.CTkFrame(hk, fg_color="transparent")
        stop_row.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(stop_row, text="Stop only:", width=72, anchor="w", font=ctk.CTkFont(size=12),
                     text_color="#8B949E").pack(side="left")
        self.stop_hotkey_entry = ctk.CTkEntry(
            stop_row, width=200, font=ctk.CTkFont(size=12), border_color="#30363D", fg_color="#0D131D",
            placeholder_text="optional, e.g. ctrl+shift+x")
        self.stop_hotkey_entry.pack(side="left", padx=(10, 8))
        if self.cfg.get("stop_hotkey"):
            self.stop_hotkey_entry.insert(0, self.cfg["stop_hotkey"])
        self.stop_hotkey_entry.bind("<FocusOut>", lambda e: self._on_stop_hotkey_commit())
        self.stop_hotkey_entry.bind("<Return>", lambda e: self._on_stop_hotkey_commit())
        ctk.CTkButton(stop_row, text="Apply", width=70, height=28, fg_color="#21262D", hover_color="#30363D",
                      command=self._on_stop_hotkey_commit).pack(side="left")

        self.switch_hotkey_selection = ctk.CTkSwitch(
            hk,
            text="Read the selected text (copies it first; with nothing selected, reads what you copied)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_hotkey_selection
        )
        if self.cfg.get("hotkey_reads_selection", True):
            self.switch_hotkey_selection.select()
        self.switch_hotkey_selection.pack(anchor="w", padx=16, pady=(4, 4))

        self.hotkey_status_lbl = ctk.CTkLabel(hk, text="", font=ctk.CTkFont(size=12), text_color="#8B949E")
        self.hotkey_status_lbl.pack(anchor="w", padx=16, pady=(0, 2))
        ctk.CTkLabel(
            hk,
            text="Default: ctrl+shift+space  |  Use Ctrl, Alt or Win with a key (F1–F24 may be used alone)  |  "
                 "Win+Shift+S is reserved by Snipping Tool",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # --- Notifications ---
        notif = self._section_card(scroll, "Notifications")
        notify_row = ctk.CTkFrame(notif, fg_color="transparent")
        notify_row.pack(fill="x", padx=16, pady=(2, 4))
        ctk.CTkLabel(notify_row, text="Windows notifications:", font=ctk.CTkFont(size=13),
                     text_color="#E6EDF3").pack(side="left", padx=(0, 10))
        self._notify_names = {"important": "Important only", "all": "All", "off": "Off"}
        self.seg_notify = ctk.CTkSegmentedButton(
            notify_row,
            values=list(self._notify_names.values()),
            command=self._on_notification_level,
            selected_color="#0E4A5C",
            selected_hover_color="#13607A",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.seg_notify.set(self._notify_names.get(self.cfg.get("notification_level", "important"), "Important only"))
        self.seg_notify.pack(side="left")
        ctk.CTkLabel(
            notif,
            text="Important only (recommended): voice & setting changes, updates and errors.  "
                 "All: also one for every read and auto-route.  Off: none.  "
                 "Also in the tray menu → Notifications.",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # --- Preferred voices ---
        pref = self._section_card(scroll, "Preferred Voices (Auto-Route)")
        ctk.CTkLabel(
            pref,
            text="When Smart Language Auto-Routing is on and the text is in another language than your "
                 "active voice, FluentVoice reads it with the voice you pick here:",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 6))

        self._build_preferred_picker(pref)
        ctk.CTkLabel(
            pref,
            text="Tip: a voice reads its own language as-is. Multilingual voices also keep English, "
                 "Spanish, French, German, Italian and Portuguese. Very short snippets keep your "
                 "active voice. The Voice & Speech test always uses the voice you selected.",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
            wraplength=860,
            justify="left",
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

        # --- Startup & Shortcuts (source install and portable EXE alike) ---
        boot = self._section_card(scroll, "Startup & Shortcuts")
        self.switch_startup = ctk.CTkSwitch(
            boot,
            text="Start FluentVoice Pro with Windows (tray icon at sign-in)",
            font=ctk.CTkFont(size=13),
            progress_color="#00D2FF",
            command=self._on_toggle_startup
        )
        self.switch_startup.pack(anchor="w", padx=16, pady=(4, 6))
        sc_row = ctk.CTkFrame(boot, fg_color="transparent")
        sc_row.pack(fill="x", padx=16, pady=(0, 4))
        self.btn_shortcuts = ctk.CTkButton(
            sc_row,
            text="Create Desktop & Start Menu Shortcuts",
            width=270,
            height=30,
            fg_color="#1F2E45",
            hover_color="#2A3B58",
            border_width=1,
            border_color="#00D2FF",
            text_color="#00D2FF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_create_shortcuts
        )
        self.btn_shortcuts.pack(side="left", padx=(0, 8))
        self.btn_remove_shortcuts = ctk.CTkButton(
            sc_row,
            text="Remove Shortcuts",
            width=140,
            height=30,
            fg_color="#21262D",
            hover_color="#30363D",
            command=self._on_remove_shortcuts
        )
        self.btn_remove_shortcuts.pack(side="left")
        from . import msix
        if msix.is_packaged():  # Microsoft Store build: Windows manages startup; the Start tile replaces shortcuts
            self.switch_startup.pack_forget()  # it can't show the StartupTask state Windows keeps
            self.btn_shortcuts.configure(text="Open Windows Startup Settings", command=msix.open_startup_settings)
            self.btn_remove_shortcuts.pack_forget()
        self.shortcuts_status_lbl = ctk.CTkLabel(
            boot,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
            justify="left",
            anchor="w"
        )
        self.shortcuts_status_lbl.pack(anchor="w", padx=16, pady=(2, 12))
        self._refresh_shortcuts_status()

        # --- Updates (same engine as About & Developer → Updates) ---
        upd = self._section_card(scroll, "Updates")
        upd_row = ctk.CTkFrame(upd, fg_color="transparent")
        upd_row.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkButton(
            upd_row,
            text="🔄 Check for Updates",
            width=170,
            height=30,
            fg_color="#1F2E45",
            hover_color="#2A3B58",
            border_width=1,
            border_color="#3FB950",
            text_color="#3FB950",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._check_updates_async(force=True),
        ).pack(side="left", padx=(0, 10))
        self.update_status_lbl_sys = ctk.CTkLabel(
            upd_row,
            text=f"Installed: v{APP_VERSION} • "
                 + ("updates from the Microsoft Store" if _is_store_build() else "GitHub Releases, SHA-256 verified"),
            font=ctk.CTkFont(size=12),
            text_color="#8B949E",
            anchor="w",
        )
        self.update_status_lbl_sys.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            upd,
            text=("The Microsoft Store installs updates for this copy." if _is_store_build()
                  else "Daily auto-check and \"Skip This Version\" are in About & Developer → Updates."),
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # --- Tips ---
        tips = self._section_card(scroll, "How to Trigger FluentVoice")
        common = (
            "• Direct Text Reader — paste/type long text, then Read Aloud.\n"
            "• Tray icon — left-click toggles speak/stop; right-click for voices and settings.\n"
            "• Global hotkey — Ctrl+Shift+Space (configurable above).\n"
        )
        if _is_store_build():
            guide = common + (
                "• Start menu → FluentVoice Pro — starts the tray, or opens this Control Center if it is running.\n"
                "• Footer Emergency Stop — always available on every Settings tab.\n"
                "• Close to Tray — hides Settings and ensures the tray icon is running.\n"
                "• Start with Windows — Windows Settings → Apps → Startup."
            )
        else:
            guide = common + (
                "• Desktop shortcut — one icon opens this Control Center (Emergency Stop is in the footer).\n"
                "• Footer Emergency Stop — always available on every Settings tab.\n"
                "• Start Menu → FluentVoice Pro — optional Stop / Restart Tray / Reader shortcuts.\n"
                "• Close to Tray — hides Settings and ensures the tray icon is running.\n"
                "• Start with Windows — Startup & Shortcuts card above (tray icon at every sign-in).\n"
                "• Explorer (installed version) — right-click desktop/folder background → FluentVoice Pro (Read Aloud)."
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

        card = SmoothScrollableFrame(
            tab,
            fg_color="#182234",
            corner_radius=10,
            scrollbar_button_color="#30363D",
            scrollbar_button_hover_color="#00D2FF",
        )
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
            "• FluentVoice Pro™ — Windows 11/10 text-to-speech & read-aloud tray suite\n"
            "• ClipFlow Pro — clipboard history manager for GNOME Shell\n"
            "• Comfort Control (EaseHub) — GNOME Shell panel menu for power, screenshots & updates\n"
            "• Linux Numeric Date & Clock — numeric date and 24-hour clock for the GNOME top bar"
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

        # Updates (GitHub Releases) ------------------------------------------------
        upd = ctk.CTkFrame(card, fg_color="#121824", corner_radius=8, border_width=1, border_color="#1F6F3F")
        upd.pack(fill="x", padx=16, pady=(16, 0))
        upd_top = ctk.CTkFrame(upd, fg_color="transparent")
        upd_top.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            upd_top,
            text=f"Updates  •  Installed: v{APP_VERSION}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3",
        ).pack(side="left")
        self.btn_check_updates = ctk.CTkButton(
            upd_top,
            text="🔄 Check for Updates",
            width=170,
            height=30,
            fg_color="#1F2E45",
            hover_color="#2A3B58",
            border_width=1,
            border_color="#3FB950",
            text_color="#3FB950",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._check_updates_async(force=True),
        )
        self.btn_check_updates.pack(side="right")
        self.update_status_lbl = ctk.CTkLabel(
            upd,
            text="Official releases are GitHub Artifact Attested and SHA-256 verified before install.",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
            wraplength=560,
            justify="left",
            anchor="w",
        )
        self.update_status_lbl.pack(fill="x", padx=12, pady=(2, 4))
        self.switch_update_check = ctk.CTkSwitch(
            upd,
            text="Check for updates automatically (once a day, anonymous GitHub request)",
            font=ctk.CTkFont(size=12),
            progress_color="#3FB950",
            command=self._on_toggle_update_check,
        )
        if self.cfg.get("check_updates", True):
            self.switch_update_check.select()
        if _is_store_build():  # the Store build never asks GitHub
            self.update_status_lbl.configure(text="Updates for this copy come from the Microsoft Store.")
            self.update_status_lbl.pack_configure(pady=(2, 10))
        else:
            self.switch_update_check.pack(anchor="w", padx=12, pady=(0, 10))

        # Advanced / factory reset (Settings only — not in tray)
        adv = ctk.CTkFrame(card, fg_color="#121824", corner_radius=8, border_width=1, border_color="#30363D")
        adv.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            adv,
            text="Advanced",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#E6EDF3",
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            adv,
            text="Restore voice, modulation, hotkey, automation, and preferred voices to factory defaults.",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkButton(
            adv,
            text="↺ Restore Factory Settings…",
            fg_color="#21262D",
            hover_color="#DA3633",
            border_width=1,
            border_color="#484F58",
            text_color="#E6EDF3",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_factory_reset,
        ).pack(anchor="w", padx=12, pady=(0, 12))

        ctk.CTkLabel(
            card,
            text="FluentVoice Pro™ • MIT License • Built with Python, Win32 API & CustomTkinter.\n"
                 "Name/brand claim of Nick Otmazgin; source remains free and open-source (MIT).",
            font=ctk.CTkFont(size=11),
            text_color="#8B949E",
            justify="left",
        ).pack(anchor="w", padx=16, pady=(12, 8))

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(4, 14))

        # Row 1: action buttons alone on the right
        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 10))

        btn_close = ctk.CTkButton(
            actions,
            text="Close to Tray",
            fg_color="#21262D",
            hover_color="#30363D",
            width=110,
            command=self._on_close_to_tray,
        )
        btn_close.pack(side="right")

        btn_emergency = ctk.CTkButton(
            actions,
            text="⏹ Emergency Stop",
            fg_color="#DA3633",
            hover_color="#F85149",
            text_color="#FFFFFF",
            width=150,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_emergency_stop,
        )
        btn_emergency.pack(side="right", padx=(0, 8))

        # Visible horizontal separator
        rule = ctk.CTkFrame(footer, height=2, fg_color="#484F58")
        rule.pack(fill="x", pady=(0, 10))
        rule.pack_propagate(False)

        # Row 2: status stacked on the left only (never under the buttons)
        status_col = ctk.CTkFrame(footer, fg_color="transparent")
        status_col.pack(anchor="w")

        status_lbl = ctk.CTkLabel(
            status_col,
            text="Single-Stream Engine Active • Zero Collisions",
            text_color="#3FB950",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        status_lbl.pack(anchor="w")

        self.autosave_lbl = ctk.CTkLabel(
            status_col,
            text="✓ All settings auto-saved",
            text_color="#8B949E",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.autosave_lbl.pack(anchor="w", pady=(3, 0))

    def _on_emergency_stop(self):
        """Hard-stop speech from Settings footer — primary failsafe without a second desktop icon."""
        try:
            from . import core
            core.stop_all_playback(notify=True)
        except Exception as e:
            if hasattr(self, "autosave_lbl"):
                self.autosave_lbl.configure(text=f"⚠ Stop failed: {e}", text_color="#F85149")
                return
        if hasattr(self, "autosave_lbl"):
            self.autosave_lbl.configure(text="⏹ Speech stopped immediately", text_color="#F85149")
            self.after(
                2500,
                lambda: self.autosave_lbl.configure(
                    text="✓ All settings auto-saved", text_color="#8B949E"
                ),
            )

    def _on_close_to_tray(self):
        """Hide Settings and ensure the tray daemon is alive (fixes Exit → reopen → no tray)."""
        try:
            from .lifecycle import TRAY_START_TIMEOUT_SEC, ensure_tray_running
            ok = ensure_tray_running(wait_sec=TRAY_START_TIMEOUT_SEC)  # returns as soon as the tray is up
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
                valid = ["Direct Text Reader", "Voice & Speech", "Voice Providers", "Automation & System", "About & Developer"]
                if tab in valid:
                    self._select_tab(tab)
                    self.lift()
                    self.focus_force()
        except Exception:
            pass

        try:
            flag = config.APP_DIR / "pending_update_popup.txt"
            if flag.exists():
                flag.unlink(missing_ok=True)
                self._select_tab("About & Developer")
                self._check_updates_async(force=True, popup=True)
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
            if hasattr(self, "seg_notify"):
                want = self._notify_names.get(fresh.get("notification_level", "important"), "Important only")
                if self.seg_notify.get() != want:
                    self._syncing_from_disk = True
                    try:
                        self.seg_notify.set(want)
                    finally:
                        self._syncing_from_disk = False
                    changed = True
            apply_switch("switch_update_check", "check_updates", True)
            apply_switch("switch_offline_only", "offline_only", False)
            apply_switch("switch_hotkey_selection", "hotkey_reads_selection", True)

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
                    label = self._label_for_voice(want_voice)
                    self._syncing_from_disk = True
                    try:
                        self._show_voice(label)
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
            self._cfg_base = copy.deepcopy(fresh)
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

    OFFLINE_GROUP = "Offline (Windows voices)"

    def _voice_groups(self) -> dict:
        """{'English': [labels…], …, 'Offline (Windows voices)': […]} in catalog order."""
        groups = {name: [label for _, label in voices.all_voices_for(fam)] for fam, name in voices.LANGUAGES.items()}
        catalog_labels = {label for _, label, _ in voices.CATALOG}
        offline = [label for label, code in self.voice_map.items()
                   if label not in catalog_labels and not voices.is_local_hd(code)]
        if offline:
            groups[self.OFFLINE_GROUP] = offline
        return groups

    def _group_of_label(self, label: str) -> str:
        for group, labels in self._voice_groups().items():
            if label in labels:
                return group
        return voices.LANGUAGES["english"]

    def _show_voice(self, label: str):
        """Point both pickers at `label` without triggering a change."""
        group = self._group_of_label(label)
        self.lang_var.set(group)
        self.voice_menu.configure(values=self._voice_groups().get(group, [label]))
        self.voice_var.set(label)
        self.voice_menu.set(label)

    def _align_test_entry(self, voice_code: str):
        rtl = voices.family_of(voice_code) in voices.RTL_FAMILIES
        self.test_entry.configure(justify="right" if rtl else "left")
        cur = self.test_entry.get()
        want = bidi_wrap_lines(cur) if rtl else bidi_strip(cur)
        if want != cur:
            self.test_entry.delete(0, "end")
            self.test_entry.insert(0, want)

    def _on_voice_language_changed(self, group):
        labels = self._voice_groups().get(group, [])
        if not labels:
            return
        current = self.voice_var.get()
        if current in labels:
            choice = current
        else:  # the preferred voice for that language, else its first voice
            fam = next((f for f, n in voices.LANGUAGES.items() if n == group), None)
            pref = (self.cfg.get("preferred_voices") or {}).get(fam) if fam else None
            pref_label = voices.label_for(pref) if pref else ""
            choice = pref_label if pref_label in labels else labels[0]
        self.voice_menu.configure(values=labels)
        self.voice_var.set(choice)
        self.voice_menu.set(choice)
        if choice != current:
            self._on_voice_changed(choice)

    def _persist_cfg(self):
        """Save only the settings changed in this window, on top of the file on disk, so a
        change made in the tray meanwhile is never overwritten."""
        changes = {k: v for k, v in self.cfg.items() if self._cfg_base.get(k) != v}
        if changes:
            self.cfg = config.update_config(changes)
            self._cfg_base = copy.deepcopy(self.cfg)

    def _on_voice_changed(self, choice):
        if self._syncing_from_disk:
            return
        vcode = self.voice_map.get(choice, "en-US-AndrewMultilingualNeural")
        self.cfg["voice"] = vcode
        self.cfg["engine"] = ("offline" if voices.is_offline(vcode) else
                              "local" if voices.is_local_hd(vcode) else "neural")
        self._persist_cfg()
        self._trigger_autosave_indicator()
        self._refresh_reader_voice_label()
        core.trigger_notification("FluentVoice Pro", f"🗣 Voice selected: {choice}")
        # Swap the preview sentence to the new voice's language unless the user typed their own.
        cur = bidi_strip(self.test_entry.get()).strip()
        if not cur or cur in voices.SAMPLE_TEXT.values():
            self.test_entry.delete(0, "end")
            self.test_entry.insert(0, voices.sample_text(vcode))
        self._align_test_entry(vcode)
        self.test_status_lbl.configure(text=f"Selected voice: {choice}", text_color="#00D2FF")

    def _on_open_windows_speech_settings(self):
        # Opens OS Speech Settings so user can install OneCore/SAPI packs.
        # Those packs then appear in FluentVoice offline voice list (not neural Edge list).
        if hasattr(self, "offline_status_lbl"):
            self.offline_status_lbl.configure(
                text="Opening Windows Speech Settings… Install a speech language pack, then return here.",
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
                    self.btn_offline.configure(state="normal", text="Install Windows Offline Voices…")
                if hasattr(self, "offline_status_lbl"):
                    self.offline_status_lbl.configure(
                        text="Windows Speech opened. After installing voices, reopen Voice & Speech to refresh the Offline list.",
                        text_color="#3FB950"
                    )
                # Refresh offline voice entries if dropdown exists
                try:
                    self.voice_map = build_full_voice_map()
                    if hasattr(self, "voice_menu"):
                        self.lang_menu.configure(values=list(self._voice_groups().keys()))
                        self._show_voice(self._label_for_voice(self.cfg.get("voice", voices.DEFAULT_VOICE)))
                except Exception:
                    pass

            self.after(0, restore_btn)

        threading.Thread(target=open_settings, daemon=True).start()

    def _on_rate_slider(self, val):
        if self._syncing_from_disk:
            return
        self.rate_val_lbl.configure(text=f"{val:.1f}x")
        self.cfg["rate_mult"] = round(val, 1)
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _on_pitch_slider(self, val):
        if self._syncing_from_disk:
            return
        pitch_int = int(round(val))
        txt = f"{pitch_int:+d}Hz (Default)" if pitch_int == 0 else f"{pitch_int:+d}Hz"
        self.pitch_val_lbl.configure(text=txt)
        self.cfg["pitch_hz"] = pitch_int
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _on_volume_slider(self, val):
        if self._syncing_from_disk:
            return
        vol = int(round(val))
        self.vol_val_lbl.configure(text=f"{vol}%")
        self.cfg["volume"] = vol
        self._persist_cfg()
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
        self.cfg["rate"] = "+0%"  # keep legacy rate string in sync
        self._persist_cfg()
        self._trigger_autosave_indicator()
        self.test_status_lbl.configure(text="Speed, pitch & volume reset (1.0x, +0Hz, 100%)", text_color="#8B949E")

    def _on_factory_reset(self):
        """Confirm, restore DEFAULT_CONFIG, then reopen Settings so every control reloads."""
        from tkinter import messagebox

        ok = messagebox.askyesno(
            "Restore Factory Settings",
            "Reset ALL FluentVoice Pro settings to factory defaults?\n\n"
            "This restores voice, speed, pitch, volume, hotkey, automation toggles,\n"
            "notifications, the Auto-Read stability buffer and Preferred Voices.\n"
            "Start with Windows and your shortcuts are not changed.\n\n"
            "This cannot be undone.",
            parent=self,
        )
        if not ok:
            return
        try:
            current_tab = self.tabview.get()
        except Exception:
            current_tab = "About & Developer"
        self.cfg = config.factory_reset_config()
        self._cfg_base = copy.deepcopy(self.cfg)
        # Soft-nudge tray to reload config on next poll
        try:
            from .lifecycle import ensure_tray_running
            ensure_tray_running(wait_sec=0.4)
        except Exception:
            pass
        self.destroy()
        open_settings_window(tab=current_tab)

    def _on_toggle_hotkey(self):
        if self._syncing_from_disk:
            return
        self.cfg["hotkey_enabled"] = self.switch_hotkey.get() == 1
        self._persist_cfg()
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
        problem = hotkeys.hotkey_problem(raw)
        if problem:
            self.autosave_lbl.configure(text=f"⚠ Hotkey '{raw}' not saved: {problem}", text_color="#F85149")
            return
        self.cfg["hotkey"] = raw
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _on_stop_hotkey_commit(self):
        if self._syncing_from_disk:
            return
        raw = (self.stop_hotkey_entry.get() or "").strip().lower().replace(" ", "").replace("++", "+")
        problem = hotkeys.hotkey_problem(raw) if raw else ""
        if problem:
            self.autosave_lbl.configure(text=f"⚠ Stop hotkey '{raw}' not saved: {problem}", text_color="#F85149")
            return
        if raw == self.cfg.get("stop_hotkey", ""):
            return
        self.cfg["stop_hotkey"] = raw
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _on_toggle_hotkey_selection(self):
        if self._syncing_from_disk:
            return
        self.cfg["hotkey_reads_selection"] = self.switch_hotkey_selection.get() == 1
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _refresh_hotkey_status(self):
        """Show whether the tray could register the hotkeys (another app may own the chord)."""
        if not hasattr(self, "hotkey_status_lbl"):
            return
        st = hotkeys.read_status() if getattr(self, "_tray_running_shown", False) else {}
        lines, bad = [], False
        for key, what in (("read", "Speak / Stop"), ("stop", "Stop")):
            e = st.get(key) or {}
            if not e.get("chord"):
                continue
            if e.get("ok"):
                lines.append(f"✔ {what}: {e['chord']}")
            else:
                bad = True
                lines.append(f"⚠ {what}: {e['chord']} — {e.get('error') or 'not registered'}; pick another")
        text = "   ".join(lines)
        if text != self.hotkey_status_lbl.cget("text"):
            self.hotkey_status_lbl.configure(text=text, text_color="#F85149" if bad else "#3FB950")

    def _on_pref_voice(self, lang_key: str, voice_code: str):
        if self._syncing_from_disk or not voice_code:
            return
        prefs = dict(self.cfg.get("preferred_voices") or {})
        prefs[lang_key] = voice_code
        self.cfg["preferred_voices"] = prefs
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _refresh_tray_status(self):
        try:
            from .lifecycle import is_tray_running
            running = is_tray_running()
            if hasattr(self, "tray_status_lbl") and running != getattr(self, "_tray_running_shown", None):
                self._tray_running_shown = running
                if running:
                    self.tray_status_lbl.configure(
                        text="● Tray daemon is running (icon should appear near the clock)",
                        text_color="#3FB950"
                    )
                else:
                    self.tray_status_lbl.configure(
                        text="○ Tray is not running — click Ensure Tray Running to start it",
                        text_color="#F85149"
                    )
        except Exception:
            pass
        try:
            self._refresh_hotkey_status()
        except Exception:
            pass
        self.after(2000, self._refresh_tray_status)

    def _refresh_shortcuts_status(self, note: str = "", color: str = "#8B949E"):
        from . import msix, shortcuts
        if msix.is_packaged():
            self.shortcuts_status_lbl.configure(
                text=note or ("Microsoft Store version: FluentVoice Pro starts with Windows after its first launch.\n"
                              "Turn this on or off in Windows Settings → Apps → Startup. Find the app in the Start menu."),
                text_color=color)
            return
        on = shortcuts.startup_enabled()
        have = shortcuts.shortcuts_installed()
        if on:
            self.switch_startup.select()
        else:
            self.switch_startup.deselect()
        self.btn_shortcuts.configure(
            text="Recreate Desktop & Start Menu Shortcuts" if have else "Create Desktop & Start Menu Shortcuts"
        )
        kind = "Portable" if shortcuts.is_frozen() else "Installed"
        where = str(shortcuts.app_dir())
        home = str(Path.home())
        if where.lower().startswith(home.lower()):
            where = "%USERPROFILE%" + where[len(home):]  # no user name in shared screenshots
        if not note:
            note = (f"{kind} copy: {where}\n"
                    f"Start with Windows: {'on' if on else 'off'} • Desktop & Start Menu shortcuts: "
                    f"{'present' if have else 'not created'}")
            if shortcuts.is_frozen():
                note += "\nMoved this folder? Just run FluentVoicePro.exe once. Shortcuts follow it automatically."
        self.shortcuts_status_lbl.configure(text=note, text_color=color)

    def _on_toggle_startup(self):
        from . import shortcuts
        want = bool(self.switch_startup.get())
        try:
            shortcuts.set_startup(want)
            self._refresh_shortcuts_status(
                "✓ FluentVoice Pro will start with Windows" if want else "✓ Removed from Windows startup",
                "#3FB950")
        except Exception as e:
            self._refresh_shortcuts_status(f"⚠ Could not change startup: {e}", "#F85149")

    def _on_create_shortcuts(self):
        from . import shortcuts
        try:
            made = shortcuts.create_shortcuts()
            self._refresh_shortcuts_status(
                f"✓ Created {len(made)} shortcuts (Desktop + Start Menu → FluentVoice Pro)", "#3FB950")
        except Exception as e:
            self._refresh_shortcuts_status(f"⚠ Could not create shortcuts: {e}", "#F85149")

    def _on_remove_shortcuts(self):
        from . import shortcuts
        try:
            shortcuts.remove_shortcuts()
            self._refresh_shortcuts_status("✓ Desktop & Start Menu shortcuts removed", "#3FB950")
        except Exception as e:
            self._refresh_shortcuts_status(f"⚠ Could not remove shortcuts: {e}", "#F85149")

    def _on_ensure_tray(self):
        from .lifecycle import TRAY_START_TIMEOUT_SEC, ensure_tray_running
        self.autosave_lbl.configure(text="↻ Starting tray…", text_color="#00D2FF")

        def work():  # off the UI thread: a cold start can take a few seconds
            ok = ensure_tray_running(wait_sec=TRAY_START_TIMEOUT_SEC)

            def done():
                self._refresh_tray_status()
                if ok:
                    self.autosave_lbl.configure(text="✓ Tray started / already running", text_color="#3FB950")
                    core.trigger_notification("FluentVoice Pro", "Tray daemon is active")
                else:
                    self.autosave_lbl.configure(text="⚠ Failed to start tray", text_color="#F85149")

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _on_restart_tray(self):
        """Ask running tray to exit, then start a fresh daemon."""
        from .lifecycle import TRAY_START_TIMEOUT_SEC, ensure_tray_running, is_tray_running
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
            ok = ensure_tray_running(wait_sec=TRAY_START_TIMEOUT_SEC)

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
        self._persist_cfg()
        self._trigger_autosave_indicator()
        state_str = "Enabled" if enabled else "Disabled"
        core.trigger_notification("FluentVoice Pro", f"⚡ Auto-Read on Copy: {state_str}")

    def _on_buffer_slider(self, val):
        if self._syncing_from_disk:
            return
        buf = round(val, 1)
        self.buf_val_lbl.configure(text=f"{buf:.1f}s")
        self.cfg["debounce_sec"] = buf
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _on_toggle_autoroute(self):
        if self._syncing_from_disk:
            return
        self.cfg["auto_route_language"] = self.switch_autoroute.get() == 1
        self._persist_cfg()
        self._trigger_autosave_indicator()
        self._refresh_reader_voice_label()

    def _on_toggle_markdown(self):
        if self._syncing_from_disk:
            return
        self.cfg["clean_markdown"] = self.switch_markdown.get() == 1
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _on_notification_level(self, name):
        if self._syncing_from_disk:
            return
        level = next((k for k, v in self._notify_names.items() if v == name), "important")
        self.cfg["notification_level"] = level
        self.cfg["show_notifications"] = level != "off"
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _on_test_speak(self):
        txt = bidi_strip(self.test_entry.get()).strip()
        if not txt:
            txt = voices.sample_text(self.cfg.get("voice", ""))
        # Always the selected voice: auto-route would swap it when the text's language differs.
        self._start_speech(txt, self.test_status_lbl, self.btn_speak, "▶  Speak Test Text", auto_route=False)

    def _on_test_stop(self):
        core.stop_all_playback()
        self._finish_speech_ui()
        self.test_status_lbl.configure(text="⏹ Speech stopped immediately", text_color="#8B949E")

    # ------------------------------------------------------------------
    # Updates (GitHub Releases) — worker thread -> after() poll, no Tk off-thread
    # ------------------------------------------------------------------
    def _on_toggle_update_check(self):
        if self._syncing_from_disk:
            return
        self.cfg["check_updates"] = self.switch_update_check.get() == 1
        self._persist_cfg()
        self._trigger_autosave_indicator()

    def _check_updates_async(self, force: bool = False, popup: bool = None):
        import queue as _queue
        from fluentvoice import updater
        if popup is None:
            popup = force
        q = _queue.Queue()
        if force and not _is_store_build():
            self._set_update_status("⏳ Checking GitHub for the latest release…", "#00D2FF")
            try:
                self.btn_check_updates.configure(state="disabled")
            except Exception:
                pass
        threading.Thread(target=lambda: q.put(updater.check_for_update(force=force)), daemon=True).start()

        def poll():
            try:
                res = q.get_nowait()
            except Exception:
                self.after(150, poll)
                return
            self._apply_update_result(res, force=force, popup=popup)
        self.after(150, poll)

    def _set_update_status(self, text: str, color: str):
        for attr in ("update_status_lbl", "update_status_lbl_sys"):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                try:
                    lbl.configure(text=text, text_color=color)
                except Exception:
                    pass

    def _apply_update_result(self, res: dict, force: bool, popup: bool):
        st = res.get("status")
        try:
            self.btn_check_updates.configure(state="normal")
        except Exception:
            pass
        if st == "update":
            self._update_info = res
            try:
                self.update_badge.configure(text=f"⬆ v{res.get('latest')} available")
                self.update_badge.pack(side="right", padx=(0, 4), pady=10)
            except Exception:
                pass
            self._set_update_status(
                f"⬆ New version v{res.get('latest')} is available (you have v{res.get('current')}).", "#3FB950")
            if popup:
                self._show_update_popup(res)
        elif st in ("current", "cached", "skipped"):
            if force:
                self._set_update_status(f"✅ You're on the latest version (v{res.get('current')}).", "#3FB950")
        elif st == "store":
            self._set_update_status("Updates for this copy come from the Microsoft Store.", "#3FB950")
            if force:
                from fluentvoice import msix
                msix.open_store_page()
        elif st == "error" and force:
            self._set_update_status("⚠ Couldn't reach GitHub (offline or rate-limited). Try again later.", "#E3B341")

    def _show_update_popup(self, info):
        from fluentvoice import updater
        if not info:
            return
        existing = getattr(self, "_update_win", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        win = ctk.CTkToplevel(self)
        self._update_win = win
        win.title("FluentVoice Pro — Update Available")
        win.geometry("600x520")
        win.configure(fg_color="#0D131D")
        win.transient(self)
        win.after(200, win.lift)

        ctk.CTkLabel(
            win,
            text=f"⬆ FluentVoice Pro v{info.get('latest')} is available",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#3FB950",
        ).pack(anchor="w", padx=18, pady=(16, 2))
        pub = (info.get("published") or "")[:10]
        ctk.CTkLabel(
            win,
            text=f"You have v{info.get('current')}  •  Released {pub}  •  ✔ GitHub Artifact Attested  •  ✔ SHA-256 checked",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E",
        ).pack(anchor="w", padx=18, pady=(0, 8))

        notes = ctk.CTkTextbox(win, fg_color="#121824", text_color="#E6EDF3", wrap="word",
                               font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8)
        notes.pack(fill="both", expand=True, padx=18, pady=4)
        notes.insert("1.0", updater.short_notes(info.get("notes", ""), max_lines=40) or "See the release page for details.")
        notes.configure(state="disabled")

        status = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=12), text_color="#00D2FF",
                              wraplength=560, justify="left", anchor="w")
        status.pack(fill="x", padx=18, pady=(6, 2))

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 16))

        def open_page():
            webbrowser.open(info.get("url") or updater.RELEASES_PAGE)

        def skip():
            updater.skip_version(info.get("latest", ""))
            try:
                self.update_badge.pack_forget()
            except Exception:
                pass
            win.destroy()

        def download():
            import queue as _queue
            q = _queue.Queue()
            btn_dl.configure(state="disabled", text="⏳ Downloading…")

            def prog(done, total):
                q.put(("p", done, total))

            threading.Thread(target=lambda: q.put(("r", updater.download_update(info, progress=prog))), daemon=True).start()

            def poll():
                last = None
                while True:
                    try:
                        last = q.get_nowait()
                    except Exception:
                        break
                    if last[0] == "r":
                        return finish(last[1])
                    _, done, total = last
                    pct = f" {done * 100 // total}%" if total else ""
                    status.configure(text=f"⏳ Downloading{pct} ({done / 1_048_576:.1f} MB)…", text_color="#00D2FF")
                if win.winfo_exists():
                    win.after(150, poll)

            win.after(150, poll)

        def install_now(path, sha=None):
            from tkinter import messagebox
            if updater.is_git_checkout():
                status.configure(text="ℹ This copy is a git checkout — update with `git pull`, then run install.ps1.",
                                 text_color="#E3B341")
                return
            if not messagebox.askyesno(
                "Install FluentVoice Pro update",
                f"Install v{info.get('latest')} now?\n\n"
                "The verified ZIP is extracted next to your current copy, the installer runs, "
                "and FluentVoice restarts. Your settings are kept.",
                parent=win,
            ):
                return
            plan = updater.prepare_install(path, info, sha256=sha)
            if not plan.get("ok"):
                status.configure(text="⚠ " + plan.get("message", "Install failed"), text_color="#F85149")
                return
            updater.launch_install(plan)
            status.configure(text=f"🚀 Installing… {plan.get('message')}", text_color="#3FB950")
            self.after(1200, self.destroy)

        def finish(res):
            if not win.winfo_exists():
                return
            if res.get("ok"):
                path = res.get("path", "")
                status.configure(
                    text=f"✔ Saved to {path}\n{res.get('message')}  •  SHA-256 {res.get('sha256', '')[:16]}…",
                    text_color="#3FB950",
                )
                if res.get("verified") and not updater.is_git_checkout():
                    btn_dl.configure(text="🚀 Install Now", state="normal", command=lambda: install_now(path, res.get("sha256")))
                else:
                    btn_dl.configure(text="📂 Show in Folder", state="normal",
                                     command=lambda: subprocess.Popen(["explorer", "/select,", path]))
                    if updater.is_git_checkout():
                        status.configure(text=status.cget("text") + "\nGit checkout detected: update with `git pull`.")
            else:
                status.configure(text="⚠ " + res.get("message", "Download failed"), text_color="#F85149")
                btn_dl.configure(state="normal", text="⬇ Retry Download")

        btn_dl = ctk.CTkButton(row, text="⬇ Download & Verify", fg_color="#238636", hover_color="#2EA043",
                               text_color="#FFFFFF", font=ctk.CTkFont(weight="bold"), command=download)
        btn_dl.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="🌐 Release Page", fg_color="#21262D", hover_color="#30363D",
                      width=130, command=open_page).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Skip This Version", fg_color="#21262D", hover_color="#30363D",
                      width=130, command=skip).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Later", fg_color="#21262D", hover_color="#30363D",
                      width=80, command=win.destroy).pack(side="right")

    # ------------------------------------------------------------------ Preferred Voices (compact)
    def _build_preferred_picker(self, parent):
        """Language ▸ Voice: one row for all 22 languages, plus a summary of what was changed."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(2, 4))
        names = list(voices.LANGUAGES.values())
        self.pref_lang_var = ctk.StringVar(value=names[0])
        self.pref_lang_menu = ctk.CTkOptionMenu(
            row, values=names, variable=self.pref_lang_var, command=lambda _n: self._refresh_pref_voice_menu(),
            width=170, height=30, corner_radius=8, fg_color="#1F2E45", button_color="#00D2FF",
            button_hover_color="#33DCFF", text_color="#E6EDF3", dropdown_fg_color="#121824",
            dropdown_hover_color="#0E4A5C", dropdown_text_color="#E6EDF3", font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w")
        self.pref_lang_menu.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row, text="→", font=ctk.CTkFont(size=14, weight="bold"), text_color="#8B949E").pack(side="left")
        self.pref_voice_var = ctk.StringVar(value="")
        self.pref_voice_menu = ctk.CTkOptionMenu(
            row, values=[""], variable=self.pref_voice_var, command=self._on_pref_voice_picked,
            height=30, corner_radius=8, fg_color="#1F2E45", button_color="#00D2FF", button_hover_color="#33DCFF",
            text_color="#E6EDF3", dropdown_fg_color="#121824", dropdown_hover_color="#0E4A5C",
            dropdown_text_color="#E6EDF3", font=ctk.CTkFont(size=12), anchor="w", width=440)
        self.pref_voice_menu.pack(side="left", padx=(8, 8))
        ctk.CTkButton(
            row, text="↺ Defaults", width=96, height=30, fg_color="#21262D", hover_color="#30363D",
            font=ctk.CTkFont(size=12), command=self._on_pref_reset).pack(side="left")
        self.pref_summary_lbl = ctk.CTkLabel(
            parent, text="", font=ctk.CTkFont(size=12), text_color="#C9D1D9", wraplength=860, justify="left",
            anchor="w")
        self.pref_summary_lbl.pack(fill="x", padx=16, pady=(4, 2))
        self._refresh_pref_voice_menu()

    def _pref_family(self) -> str:
        name = self.pref_lang_var.get()
        return next((f for f, n in voices.LANGUAGES.items() if n == name), "english")

    def _refresh_pref_voice_menu(self):
        if not hasattr(self, "pref_voice_menu"):
            return
        fam = self._pref_family()
        options = voices.all_voices_for(fam)
        labels = [label for _, label in options]
        prefs = self.cfg.get("preferred_voices") or {}
        code = voices.current_id(prefs.get(fam, voices.DEFAULT_PREFERRED[fam]))
        current = next((label for vid, label in options if vid == code), voices.label_for(code))
        if current not in labels:
            labels.append(current)
        self.pref_voice_menu.configure(values=labels)
        self.pref_voice_var.set(current)
        self._refresh_pref_summary()

    def _refresh_pref_summary(self):
        prefs = self.cfg.get("preferred_voices") or {}
        changed = [f"{voices.LANGUAGES[f]} → {voices.short_name(prefs[f])}"
                   for f in voices.LANGUAGES if prefs.get(f) and prefs[f] != voices.DEFAULT_PREFERRED[f]]
        if changed:
            text = "Changed from the defaults: " + " • ".join(changed)
        else:
            text = "All 22 languages use their default voice. Pick a language to see or change its voice."
        self.pref_summary_lbl.configure(text=text)

    def _on_pref_voice_picked(self, label):
        fam = self._pref_family()
        code = next((vid for vid, lbl in voices.all_voices_for(fam) if lbl == label), "")
        self._on_pref_voice(fam, code)
        self._refresh_pref_summary()

    def _on_pref_reset(self):
        self.cfg["preferred_voices"] = dict(voices.DEFAULT_PREFERRED)
        self._persist_cfg()
        self._trigger_autosave_indicator()
        self._refresh_pref_voice_menu()

    # ------------------------------------------------------------------ Voice Providers tab
    def _provider_text(self, parent, text, color="#C9D1D9", size=12, pady=(0, 6)):
        lbl = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=size), text_color=color,
                           wraplength=860, justify="left", anchor="w")
        lbl.pack(fill="x", padx=16, pady=pady)
        return lbl

    def _small_button(self, parent, text, command, accent=False, width=110):
        return ctk.CTkButton(
            parent, text=text, width=width, height=28, command=command,
            fg_color="#00D2FF" if accent else "#21262D", hover_color="#33DCFF" if accent else "#30363D",
            text_color="#080C14" if accent else "#E6EDF3", font=ctk.CTkFont(size=12, weight="bold" if accent else "normal"))

    def _populate_providers_tab(self):
        scroll = SmoothScrollableFrame(
            self.tab_providers, fg_color="transparent", scrollbar_button_color="#30363D",
            scrollbar_button_hover_color="#00D2FF")
        scroll.pack(fill="both", expand=True)
        self._dl = None  # the download in progress: {"voice", "done", "total", "error", "finished", "cancel"}

        # --- Privacy ---
        priv = self._section_card(scroll, "🛡 Privacy: where your text goes")
        self._provider_text(
            priv,
            "• Online HD voices (Microsoft) send the text being read to Microsoft's online speech service.\n"
            "• Offline voices (Piper, Kokoro and Windows) create the speech on this PC: the text never leaves it.\n"
            "• With every voice, copied passwords, keys and text marked private by password managers are skipped "
            "and never read or sent anywhere.")
        self.switch_offline_only = ctk.CTkSwitch(
            priv, text="Offline only: never send text to the internet (offline HD or Windows voices read everything)",
            font=ctk.CTkFont(size=13), progress_color="#3FB950", command=self._on_toggle_offline_only)
        if self.cfg.get("offline_only", False):
            self.switch_offline_only.select()
        self.switch_offline_only.pack(anchor="w", padx=16, pady=(0, 4))
        self._provider_text(
            priv, "Also in the tray menu. Each language then uses its Preferred Voice if it is offline, else a "
                  "downloaded offline HD voice, else an installed Windows voice.", color="#8B949E", size=11,
            pady=(0, 12))

        # --- Microsoft online voices ---
        ms = self._section_card(scroll, "☁ Microsoft online HD voices (80 voices • 22 languages • internet needed)")
        self._provider_text(
            ms,
            "The most natural voices, the same ones Microsoft Edge's Read Aloud uses. FluentVoice reaches them "
            "through the open-source edge-tts library.\n"
            "Rights: this is not an official Microsoft service for other apps and Microsoft can change or stop it "
            "at any time. Fine for personal reading; for publishing or selling audio, use Microsoft's official "
            "paid service (Azure AI Speech) instead. FluentVoice is not affiliated with Microsoft.\n"
            "If these voices stop working, FluentVoice continues with an offline HD voice or a Windows voice.",
            pady=(0, 12))

        # --- Piper ---
        piper = self._section_card(scroll, "🖥 Piper offline HD voices (free download • on this PC)")
        piper_ok = localtts.engine_available("piper")
        self._provider_text(
            piper,
            "Natural voices that run on this PC, made by the Open Home Foundation's Piper project (used by Home "
            "Assistant and the NVDA screen reader). About 60–115 MB each, downloaded only when you choose a voice, "
            "from the official Piper voice library, and checked against a fixed SHA-256 fingerprint before use.\n"
            "Licences were checked voice by voice: ✅ Free to use, or 🏠 Personal use only (fine for reading to "
            "yourself, not for publishing or selling the audio).")
        if not piper_ok:
            self._provider_text(piper, "⚠ The Piper engine is not installed in this copy (pip install piper-tts).",
                                color="#E3B341")
        prow = ctk.CTkFrame(piper, fg_color="transparent")
        prow.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(prow, text="Language:", font=ctk.CTkFont(size=12), text_color="#C9D1D9").pack(side="left")
        piper_langs = [voices.LANGUAGES[f] for f in voices.LANGUAGES
                       if any(v["provider"] == "piper" for v in localtts.voices_for(f))]
        self.piper_lang_var = ctk.StringVar(value=piper_langs[0])
        ctk.CTkOptionMenu(
            prow, values=piper_langs, variable=self.piper_lang_var, command=lambda _n: self._render_provider_rows(),
            width=170, height=28, fg_color="#1F2E45", button_color="#00D2FF", button_hover_color="#33DCFF",
            text_color="#E6EDF3", dropdown_fg_color="#121824", dropdown_hover_color="#0E4A5C",
            font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(8, 0))
        self._provider_text(
            piper, "Quality varies by language: English and the European voices are very good; Hebrew, Arabic, "
                   "Korean, Icelandic and the Indian-language voices are clear but more basic than the Microsoft "
                   "voices. No offline HD voice yet for Chinese, Japanese, Thai, Tamil, Gujarati or Kannada (they "
                   "keep the online and Windows voices); Hindi has Kokoro voices below.", color="#8B949E", size=11,
            pady=(2, 4))
        self.piper_rows = ctk.CTkFrame(piper, fg_color="transparent")
        self.piper_rows.pack(fill="x", padx=12, pady=(0, 10))

        # --- Kokoro ---
        kok = self._section_card(scroll, "✨ Kokoro offline HD voices (one 350 MB pack • 28 voices • on this PC)")
        self._provider_text(
            kok,
            "Very natural voices (Kokoro-82M, Apache-2.0: free for any use) for US & UK English, Spanish, French, "
            "Italian, Portuguese and Hindi. One download of 350 MB from the official sherpa-onnx "
            "release, checked against a fixed SHA-256 fingerprint. Needs a reasonably fast PC (it computes about "
            "2–3× faster than real time on a modern CPU). Kokoro voices named after other companies' voices are "
            "left out.")
        if not localtts.engine_available("kokoro"):
            self._provider_text(kok, "⚠ The Kokoro engine is not installed in this copy (pip install sherpa-onnx).",
                                color="#E3B341")
        self.kokoro_rows = ctk.CTkFrame(kok, fg_color="transparent")
        self.kokoro_rows.pack(fill="x", padx=12, pady=(0, 10))

        # --- download progress (shared) ---
        self.dl_status_lbl = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=12, weight="bold"),
                                          text_color="#00D2FF", anchor="w")
        self.dl_status_lbl.pack(fill="x", padx=24, pady=(0, 2))

        # --- Windows voices ---
        win = self._section_card(scroll, "💻 Windows offline voices (built into Windows)")
        n_win = len([d for _, d in core.get_installed_sapi_voices()])
        self._provider_text(
            win,
            f"{n_win} installed on this PC. They come with Windows (more in Windows Settings → Time & language → "
            "Speech), run offline and are the last fallback. Licensed with Windows for use on this PC.")
        self._small_button(win, "Install more Windows voices…", self._on_open_windows_speech_settings,
                           width=220).pack(anchor="w", padx=16, pady=(0, 12))

        # --- Legal ---
        legal = self._section_card(scroll, "⚖ Licences, rights & disclaimer")
        self._provider_text(
            legal,
            "• FluentVoice Pro's own code is MIT-licensed. The portable EXE also contains open-source components "
            "under their own licences (including GPL-3.0 parts of the Piper engine), listed in THIRD_PARTY_NOTICES.\n"
            "• Offline HD voices keep the licence of their recordings (shown next to each voice; full list in "
            "VOICE_LICENSES). CC BY / BY-SA voices: credit the source if you share audio made with them.\n"
            "• You are responsible for the rights to the text you have read aloud and for how you use any audio.\n"
            "• Microsoft, Windows and Microsoft Edge are trademarks of Microsoft Corporation. FluentVoice Pro is "
            "independent and not affiliated with, sponsored or endorsed by Microsoft, Piper or Kokoro.")
        lrow = ctk.CTkFrame(legal, fg_color="transparent")
        lrow.pack(fill="x", padx=16, pady=(0, 12))
        self._small_button(lrow, "Voice licences", lambda: webbrowser.open(VOICE_LICENSES_URL), width=150).pack(
            side="left", padx=(0, 8))
        self._small_button(lrow, "Third-party notices", lambda: webbrowser.open(THIRD_PARTY_URL), width=170).pack(
            side="left")

        self._render_provider_rows()

    def _licence_badge(self, v) -> tuple[str, str]:
        return ("✅ Free to use", "#3FB950") if v["kind"] == "free" else ("🏠 Personal use only", "#E3B341")

    def _render_provider_rows(self):
        """(Re)draw the Piper rows for the chosen language and the Kokoro pack row."""
        busy = self._dl is not None and not self._dl.get("finished")
        for frame in (self.piper_rows, self.kokoro_rows):
            for w in frame.winfo_children():
                w.destroy()
        name = self.piper_lang_var.get()
        fam = next((f for f, n in voices.LANGUAGES.items() if n == name), "english")
        for v in localtts.voices_for(fam):
            if v["provider"] != "piper":
                continue
            installed = localtts.is_installed(v["id"])
            row = ctk.CTkFrame(self.piper_rows, fg_color="#121A28", corner_radius=8)
            row.pack(fill="x", pady=3)
            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(6, 0))
            ctk.CTkLabel(top, text=voices.label_for(v["id"]).replace(" · Piper Offline", ""),
                         font=ctk.CTkFont(size=13, weight="bold"), text_color="#E6EDF3").pack(side="left")
            badge, color = self._licence_badge(v)
            ctk.CTkLabel(top, text=f"  {badge}", font=ctk.CTkFont(size=12), text_color=color).pack(side="left")
            size_mb = localtts.download_size(v["id"]) / 1e6
            if installed:
                self._small_button(top, "Remove", lambda i=v["id"]: self._on_remove_voice(i), width=80).pack(
                    side="right")
                self._small_button(top, "▶ Try", lambda i=v["id"]: self._on_try_voice(i), accent=True,
                                   width=70).pack(side="right", padx=(0, 6))
                ctk.CTkLabel(top, text="✓ Downloaded  ", font=ctk.CTkFont(size=12), text_color="#3FB950").pack(
                    side="right")
            else:
                b = self._small_button(top, f"Download {size_mb:.0f} MB", lambda i=v["id"]: self._on_download_voice(i),
                                       accent=True, width=140)
                b.pack(side="right")
                if busy:
                    b.configure(state="disabled")
            ctk.CTkLabel(row, text=f"Licence: {v['licence']} • {v['source']}", font=ctk.CTkFont(size=11),
                         text_color="#8B949E", anchor="w", justify="left", wraplength=820).pack(
                fill="x", padx=10, pady=(0, 6))

        # Kokoro: one pack for all its voices
        kv = next(v for v in localtts.VOICES if v["provider"] == "kokoro")
        installed = localtts.is_installed(kv["id"])
        row = ctk.CTkFrame(self.kokoro_rows, fg_color="#121A28", corner_radius=8)
        row.pack(fill="x", pady=3)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(top, text="Kokoro voice pack", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#E6EDF3").pack(side="left")
        ctk.CTkLabel(top, text="  ✅ Free to use (Apache-2.0)", font=ctk.CTkFont(size=12),
                     text_color="#3FB950").pack(side="left")
        if installed:
            self._small_button(top, "Remove", lambda: self._on_remove_voice(kv["id"]), width=80).pack(side="right")
            kokoro_labels = {voices.label_for(v["id"]): v["id"] for v in localtts.VOICES if v["provider"] == "kokoro"}
            self.kokoro_try_var = ctk.StringVar(value=next(iter(kokoro_labels)))
            self._small_button(top, "▶ Try", lambda: self._on_try_voice(kokoro_labels[self.kokoro_try_var.get()]),
                               accent=True, width=70).pack(side="right", padx=(0, 6))
            ctk.CTkOptionMenu(
                top, values=list(kokoro_labels), variable=self.kokoro_try_var, width=330, height=28,
                fg_color="#1F2E45", button_color="#00D2FF", button_hover_color="#33DCFF", text_color="#E6EDF3",
                dropdown_fg_color="#121824", dropdown_hover_color="#0E4A5C", font=ctk.CTkFont(size=12)).pack(
                side="right", padx=(0, 6))
        else:
            b = self._small_button(top, "Download 350 MB", lambda: self._on_download_voice(kv["id"]), accent=True,
                                   width=150)
            b.pack(side="right")
            if busy:
                b.configure(state="disabled")

    def _on_download_voice(self, voice_id):
        from tkinter import messagebox
        if self._dl is not None and not self._dl.get("finished"):
            return
        v = localtts.info(voice_id)
        if v is None:
            return
        if not localtts.engine_available(v["provider"]):
            messagebox.showwarning("Engine missing", f"The {localtts.PROVIDER_NAMES[v['provider']]} engine is not "
                                   "installed in this copy of FluentVoice Pro.", parent=self)
            return
        if v["kind"] == "personal":
            ok = messagebox.askyesno(
                "Personal use only",
                f"{voices.label_for(voice_id)}\n\nLicence: {v['licence']}\nSource: {v['source']}\n\n"
                "This voice may be used for personal reading only: not for publishing, broadcasting or selling "
                "audio made with it.\n\nDownload it for personal use?", parent=self)
            if not ok:
                return
        import threading as _th
        state = {"voice": voice_id, "done": 0, "total": localtts.download_size(voice_id), "error": None,
                 "finished": False, "cancel": _th.Event()}
        self._dl = state

        def progress(done, total):
            state["done"], state["total"] = done, total

        def worker():
            try:
                localtts.install(voice_id, progress=progress, cancel=state["cancel"])
            except localtts.Cancelled:
                state["error"] = "cancelled"
            except Exception as e:  # network error, checksum mismatch, unsafe archive, disk full…
                state["error"] = str(e) or type(e).__name__
            state["finished"] = True

        _th.Thread(target=worker, name="fv-voice-download", daemon=True).start()
        self._render_provider_rows()
        self.after(250, self._poll_download)

    def _poll_download(self):
        st = self._dl
        if st is None:
            return
        name = voices.short_name(st["voice"]) if st["voice"].startswith("piper:") else "Kokoro pack"
        if not st["finished"]:
            pct = 100 * st["done"] / st["total"] if st["total"] else 0
            self.dl_status_lbl.configure(
                text=f"⬇ Downloading {name}: {st['done'] / 1e6:.0f} / {st['total'] / 1e6:.0f} MB ({pct:.0f}%)",
                text_color="#00D2FF")
            self.after(250, self._poll_download)
            return
        if st["error"] == "cancelled":
            self.dl_status_lbl.configure(text=f"Download of {name} cancelled.", text_color="#8B949E")
        elif st["error"]:
            self.dl_status_lbl.configure(text=f"⚠ {name}: download failed ({st['error']}). Nothing was installed.",
                                         text_color="#F85149")
        else:
            self.dl_status_lbl.configure(text=f"✓ {name} downloaded, verified and ready (works offline).",
                                         text_color="#3FB950")
            core.trigger_notification("FluentVoice Pro", f"✓ Offline HD voice ready: {name}")
        self._dl = None
        self._refresh_voice_lists()
        self._render_provider_rows()

    def _on_remove_voice(self, voice_id):
        from tkinter import messagebox
        v = localtts.info(voice_id)
        what = "the Kokoro pack (all 28 Kokoro voices)" if v["provider"] == "kokoro" else voices.label_for(voice_id)
        if not messagebox.askyesno("Remove offline voice", f"Delete the downloaded files of {what}?\n\n"
                                   "You can download it again at any time.", parent=self):
            return
        core.stop_all_playback(notify=False)
        localtts.remove(voice_id)
        self.dl_status_lbl.configure(text=f"Removed {what}.", text_color="#8B949E")
        self._refresh_voice_lists()
        self._render_provider_rows()

    def _on_try_voice(self, voice_id):
        if self._dl is not None and not self._dl.get("finished"):
            return
        sample = voices.sample_text(voice_id)
        self.dl_status_lbl.configure(text=f"▶ {voices.label_for(voice_id)}", text_color="#00D2FF")
        threading.Thread(target=lambda: core.speak_text(sample, voice=voice_id), name="fv-try-voice",
                         daemon=True).start()

    def _on_toggle_offline_only(self):
        if self._syncing_from_disk:
            return
        on = self.switch_offline_only.get() == 1
        self.cfg["offline_only"] = on
        self._persist_cfg()
        self._trigger_autosave_indicator()
        self._refresh_reader_voice_label()
        core.trigger_notification("🛡 Privacy", "Offline only: text stays on this PC" if on else
                                  "Online HD voices allowed again")

    def _refresh_voice_lists(self):
        """After a download / removal: rebuild every voice picker."""
        try:
            self.voice_map = build_full_voice_map()
            if hasattr(self, "voice_menu"):
                self.lang_menu.configure(values=list(self._voice_groups().keys()))
                self._show_voice(self._label_for_voice(self.cfg.get("voice", voices.DEFAULT_VOICE)))
            self._refresh_pref_voice_menu()
            self._refresh_reader_voice_label()
        except Exception:
            pass

    def _label_for_voice(self, code: str, default: str | None = None) -> str:
        """Exact match first (substring matching mislabeled voices), then loose match."""
        for label, c in self.voice_map.items():
            if c == code:
                return label
        for label, c in self.voice_map.items():
            if c.lower() in (code or "").lower() or (code or "").lower() in c.lower():
                return label
        return default if default is not None else code


def open_settings_window(tab="Voice & Speech"):
    if focus_existing_settings_window(preferred_tab=tab):
        return
    app = FluentVoiceSettingsWindow(initial_tab=tab)
    app.mainloop()

if __name__ == "__main__":
    initial_tab = sys.argv[1] if len(sys.argv) > 1 else "Voice & Speech"
    open_settings_window(tab=initial_tab)
