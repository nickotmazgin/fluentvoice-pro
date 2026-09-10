# Changelog

All notable changes to **FluentVoice Pro** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.14] - 2026-09-10

### Fixed
- **Speech modulation reset**: Also clears the legacy `rate` config string to `+0%` so reset is fully consistent with defaults.

### Added
- **Restore Factory Settings**: About & Developer → Advanced button (with confirmation) restores all settings to factory defaults and reloads the Control Center. Not added to the tray menu.

---

## [1.4.13] - 2026-09-10

### Fixed
- **Settings footer collision**: Emergency Stop / Close to Tray sit on their own row above a clear horizontal divider; status + auto-save stack on the left underneath so text never sits beside or under the buttons.

---

## [1.4.12] - 2026-09-10

### Fixed
- **Settings footer collision**: Moved Emergency Stop / Close to Tray onto their own row above a horizontal divider; status + auto-save sit on a separate line underneath so text can never crowd the buttons.

---

## [1.4.11] - 2026-09-10

### Fixed
- **Settings footer layout**: Status + auto-save now stack on the left with a clear vertical divider before Emergency Stop / Close to Tray, so long status strings never collide with the buttons.

---

## [1.4.10] - 2026-09-10

### Fixed
- **Settings footer spacing**: Separated status/auto-save text from Emergency Stop with a vertical divider and dedicated left/right layout so messages never crowd the action buttons.

---

## [1.4.9] - 2026-09-10

### Changed
- **One desktop icon only**: Removed the separate Desktop "Emergency Stop" shortcut. Stop controls belong in the Settings UI (and optional Start Menu failsafes), not as a second app icon on the desktop.

### Added
- **Settings footer Emergency Stop**: Always-visible **Emergency Stop** button on every Settings tab for instant speech halt without the tray icon.

---

## [1.4.8] - 2026-09-10

### Fixed
- **System tray visibility**: Stopped `EnumWindows`/`SetWindowTheme` from mutating pystray notification HWNDs (caused silent tray disappearance under `pythonw`).
- **Honest tray diagnostics**: Startup now logs HWND + visibility, promotes notify-icon entries to always-show, and opens Settings as a failsafe if registration cannot be confirmed.
- **Multi-resolution tray icon**: Packaged crisp 16/24/32/48/64 RGBA frames for Windows 11 DPI scaling.

### Added
- **Emergency failsafe shortcuts**: Desktop + Start Menu entries for Settings, Emergency Stop Speech, Direct Text Reader, Toggle Speak/Stop, and Restart Tray (`fluentvoice --restart-tray`).
- **CLI `--restart-tray`**: Restarts the tray daemon cleanly when the icon is missing or stuck.

---

## [1.4.7] - 2026-09-10

### Fixed
- **Setuptools Flat-Layout Package Discovery**: Added `[tool.setuptools.packages.find]` to `pyproject.toml` so `pip install -e .` and `pip install .` succeed without flat-layout package ambiguity errors.
- **Global CLI Entry Point Registration**: Updated `install.ps1` to register `fluentvoice` in Python `Scripts` automatically via `pip install -e . --no-deps`.
- **Complete Clipboard Immunity**: Inherits the critical clipboard lock fix, zero-lock Win32 sequence monitoring (`GetClipboardSequenceNumber`), and SAPI `CoInitialize` COM threading safety from v1.4.6.

---

## [1.4.6] - 2026-09-10

### Fixed
- **Critical Clipboard Lock Bug**: Fixed unhandled format exceptions in `core.get_clipboard_text()` when non-text data (screenshots, images, files, or binary) was copied. Added format pre-checks (`CF_UNICODETEXT` / `CF_TEXT`), 5-stage retry backoff, and guaranteed unlock via a `try ... finally: CloseClipboard()` block. This permanently resolves system-wide clipboard lockups and empty Windows Clipboard History (`Win + V`) issues.
- **Zero-Lock Clipboard Sequence Monitoring**: Replaced aggressive polling in `tray.clipboard_monitor_loop()` with native Win32 `user32.GetClipboardSequenceNumber()`. The daemon now checks a lightweight kernel counter without acquiring clipboard locks or causing contention with user copy operations.
- **Config Disk I/O Throttling**: Cached configuration in tray monitoring loop with a 2-second heartbeat instead of reading `config.json` from disk every 500ms.
- **COM Apartment Threading**: Added `pythoncom.CoInitialize()` before SAPI `SpVoice` initialization and playback in worker threads, preventing `0x800401F0` (`CO_E_NOTINITIALIZED`) exceptions.

### Added
- **Clipboard Safety Unit Tests**: Added `tests/test_clipboard.py` covering Unicode text readback, empty clipboard handling, non-text safety, and verifying zero lock leaks across threads.

---

## [1.4.5] - 2026-09-09

### Fixed
- **Source ZIP packaging**: include `SECURITY.md`, `PRIVACY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SUPPORT.md` in `scripts/create-release-zips.ps1` (missed in v1.4.4).

---

## [1.4.4] - 2026-09-09

### Docs / Packaging
- **Release ZIP includes** community & trust docs (`SECURITY.md`, `PRIVACY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, SUPPORT — fully wired in **1.4.5** packager).
- **Contain-fit social preview** (1280×640) so the collage is fully visible in GitHub OG / link cards (no side crop).
- **Repo hardening**: release immutability, CodeQL default setup, Dependabot malware + grouped updates, branch/tag rulesets, Actions bumps (`checkout`/`setup-python`/`attest-build-provenance`).

### Note
- No intentional app/runtime behavior changes vs **1.4.3** — this is a packaging + trust/docs release. Portable EXE is rebuilt + re-attested for the new tag.

---

## [1.4.3] - 2026-09-09

### Docs
- **HD screenshots + collage** under `screenshots/v1.4.3/` (Settings tabs, Automation bottom, dark tray menu, tray/desktop icons) with a peer-style README Screenshots gallery.
- **Windows trust guide** (`docs/WINDOWS_TRUST.md`) — SmartScreen Unblock, App Control, firewall (outbound HTTPS only), attestation vs Authenticode.
- **Release packaging**: attested source ZIP + portable PyInstaller ZIP (`scripts/create-release-zips.ps1`, Actions `release-publish.yml`).
- **Community / trust parity** with sibling repos: `SECURITY.md`, `PRIVACY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.github/FUNDING.yml`, issue/PR templates, SUPPORT, CODEOWNERS, Dependabot (pip + Actions).

### Fixed
- **Blank Settings tabs**: CustomTkinter `CTkTabview.set()` races a delayed `grid_forget`; Settings now re-grids the active tab after map (Voice/Automation content no longer empty on first open).
- **Close to Tray after Exit**: Desktop/Settings no longer leaves you without a tray icon. Opening Settings (or clicking **Close to Tray**) now **ensures the tray daemon is running**.
- **Tray dark menus (session flake)**: Re-applies ForceDark + FlushMenuThemes periodically and sets immersive dark mode on process windows for stronger hover contrast.

### Added
- **Ensure Tray / Restart Tray** controls on Automation & System (plus tray status indicator).
- **Global hotkey** (default `Ctrl+Shift+Space`; configurable; Win+Shift+S avoided — reserved by Snipping Tool).
- **Volume slider** in Voice & Speech (wired to neural MCI + edge-tts + offline SAPI).
- **Spanish / French / German / Italian auto-route** (langdetect + heuristic fallback) — no longer dumps all Latin text to English voice.
- **Per-language preferred voices** (e.g. Avri vs Hila, Alvaro vs Dalia).
- **Unit tests** for text cleaner + language detect (`tests/`).
- **PyInstaller script** (`scripts/build_exe.ps1`) for a single packaged app folder.
- **Smoke-test checklist** (`docs/SMOKE_TEST.md`) for release verification.
- **CI validate workflow** + **release attestations** (Sigstore / green GitHub Release stamps).

---

## [1.4.2] - 2026-09-09

### Fixed
- **Tray menu dark theme & hover contrast**: Restored real `uxtheme` ordinal dark-mode APIs (`SetPreferredAppMode` / `FlushMenuThemes`). Fixes white menus with barely-visible khaki/beige hover highlights.
- **Voice dropdown proportions**: Active Voice Profile control uses a fixed coherent width with a cyan chevron accent (no more full-bleed cyan bar + narrower popup mismatch).
- **Offline Voices button responsiveness**: Opens `ms-settings:speech` asynchronously with instant "Opening…" feedback (no more stuck `os.system` feel).

### Added
- **Direct Text Reader voice awareness**: Shows the active reading voice + Smart auto-route state, with a **Change Voice →** button that jumps to Voice & Speech.

---

## [1.4.1] - 2026-09-09

### Fixed
- **Markdown Cleaner Toggle Actually Applied**: `clean_markdown` setting is now respected in `speak_text()` (was saved in Settings but previously ignored during speech).
- **Offline Speak Toggle Reliability**: Offline SAPI now uses synchronous speak so `_is_speaking` stays accurate; tray click-to-stop works during offline playback.
- **Smart Auto-Route + Offline Engine Conflict**: Language auto-routing now forces neural engine when switching to Hebrew/Arabic/Japanese voices (no longer tries to feed neural voice IDs into offline SAPI).
- **Language Mismatch Notices**: When auto-routing is off, mismatch toasts cover Hebrew, Arabic, and CJK (not only Hebrew).
- **GUI Thread Safety**: Direct Text Reader and Test Voice status labels update via `after(0, ...)` from worker threads (avoids intermittent CustomTkinter/Tk crashes).
- **Tray Tab Switching**: Opening Direct Text Reader / Settings / About while the Control Center is already open now switches to the requested tab instead of only focusing the window.
- **README Stale Installer References**: Removed outdated `v1.1.0` ZIP name and dual-desktop-shortcut instructions; documented `--reader`.

---

## [1.4.0] - 2026-09-08

### Added
- **Dedicated Direct Text Reader & Scratchpad Window**:
  - Full-featured multi-line text scratchpad integrated directly into the Control Center with a dedicated **Direct Text Reader** tab.
  - Quick action toolbar: **📋 Paste Clipboard**, **🗑️ Clear**, **▶️ Read Aloud**, and **⏹️ Stop**.
  - Real-time text analytics: displays live word count, character count, and automatically detects text language (Hebrew 🇮🇱, Arabic 🇸🇦, Japanese/CJK 🇯🇵, English/Latin 🌐).
  - 1-Click System Tray shortcut: **📋 Direct Text Reader...** opens directly to the scratchpad.
  - CLI flag `--reader` / `-r` for direct shell and script access.
- **Immediate Synthesis Queue & Preparation Feedback**:
  - Solved user waiting ambiguity during neural audio synthesis (~2–6s remote generation):
  - Sends immediate notification `⏳ Synthesizing speech: "<snippet>"` the instant speech is requested so users know processing has started.
  - Transitions to `🔊 Speaking: "<snippet>"` as soon as playback commences.
  - Real-time status in GUI: shows `⏳ Synthesizing voice... Connecting to neural engine...` followed by `✔️ Speech playback active (Zero Collisions)`.
- **Smart Language Detection & Voice Auto-Routing**:
  - Automatic character script analysis detects when copied or pasted text is Hebrew, Arabic, Japanese/CJK, or English/Latin.
  - When enabled, automatically routes Hebrew text to `Avri (Hebrew HD)` (`he-IL-AvriNeural`) or other native models without requiring manual voice switching.
  - Displays language routing notifications (e.g. `🇮🇱 Hebrew detected: Auto-routed to Avri (Hebrew HD)`).
  - Can be toggled on/off in **Settings -> Automation & System** (`Smart Language Auto-Routing`).
  - Provides language mismatch warning toasts when auto-routing is disabled.
- **Advanced Text & Character Sanitizer (PDF, OCR, Hebrew Niqqud, Unicodes, Code)**:
  - Unicode NFKC normalization: cleans composite glyphs, full-width characters, and ligatures.
  - Strips invisible zero-width characters (`\u200B-\u200D`, `\uFEFF`, soft hyphens `\u00AD`) and bidirectional markers (`\u200E`, `\u200F`, `\u202A-\u202E`).
  - Strips non-printable control characters that could crash SAPI COM objects or cause silent audio gaps.
  - Heuristic repair for broken PDF and OCR hyphenated line breaks (`inter-\nnational` -> `international`).
  - Merges soft line wraps from PDFs into smooth conversational sentences.
  - Replaces raw web links (`https://...`) with spoken domain names (`link to domain.com`).
  - Translates bullet points and unicode symbols into natural conversational pauses.
  - Safely handles Hebrew Niqqud (vowels) without corrupting text stream.
- **Configurable Auto-Read Stability Buffer Slider**:
  - Added user control over clipboard debounce delay (0.3s to 1.5s, default 0.6s) in **Settings -> Automation & System**.

### Fixed
- **Win32 Menu Mnemonic Escaping (Double-Space Glitch)**:
  - Fixed Win32 menu accelerator ampersand stripping: replaced single `&` with escaped `&&` in `pystray` menu definitions, restoring crisp literal ampersands and eliminating double-space gaps (`⚙️ Settings && Control Center...`, `ℹ️ About && Credits...`, `💖 Donate && Support...`, `🌐 GitHub Repository && Docs...`).
- **Universal Welcoming Preview Greeting**:
  - Replaced personalized `"Hello Nick"` placeholder with universal friendly greeting: `"Welcome to FluentVoice Pro! High-definition natural speech synthesis is active."`
- **Repository Asset Cleanup**:
  - Removed outdated screenshot images from the repository and cleaned `README.md` image references.

---

## [1.3.1] - 2026-09-08

### Added
- **Single-Instance Settings Window Focus (Duplicate Stacking Prevention)**:
  - Fixed duplicate window bug: clicking the desktop icon or tray menu when Settings is already open now restores and brings the existing window to the foreground instantly with zero duplicate windows.
- **Voice Pitch & Tone Modulation Slider (`-40Hz` to `+40Hz`)**:
  - Fine-tune vocal pitch between deeper and higher tones in real-time.
  - Added a 1-click **↺ Reset Speed & Pitch to Defaults** button (Speed: 1.0x, Pitch: +0Hz).
- **Instant Auto-Save Visual Indicator**:
  - Live feedback in the Settings footer: shows `✓ Settings Saved` on any change, confirming immediate persistence to `config.json`.
- **Integrated Bug Reporting & Feedback Channels**:
  - Added direct **🐛 Report Bug / Feedback** button in the Settings window and **🐛 Report an Issue / Feedback...** in the tray menu.
  - Added GitHub Issue templates (`bug_report.md`, `feature_request.md`, `config.yml`).
- **Multi-Resolution Icon Layers (16px to 256px)**:
  - Re-encoded `icon.ico` and `tray_icon.ico` with full 8-layer embedded resolutions (16, 20, 24, 32, 48, 64, 128, 256) for crisp rendering across all Windows DPI scaling factors.

---

## [1.3.0] - 2026-09-08

### Added
- **Native Windows Toast & Popup Notification System**:
  - Live toast / balloon alerts for key actions: Auto-Read on Copy (Enabled/Disabled), voice switching with voice name, active speech playback with text snippet preview, and instant playback stop.
  - Full user toggle switch in **Settings -> Automation & System**: easily turn Windows notifications on or off.
  - **1-Click System Tray Toggle**: Added `🔔 Windows Notifications` directly into the tray context menu for instant access.
- **Intelligent Speech Synthesis Error Handling & Network Notices**:
  - Automatically notifies the user if cloud neural speech is unreachable, gracefully falling back to local Windows offline voices.
  - Informs the user with an actionable alert if no local offline voices are installed on the system.
  - Added live synthesis status indicators (`Ready`, `Synthesizing...`, `Playback Active`, `Fallback Active`, `Error`) directly in the Settings GUI preview sandbox.
- **Dynamic Local Offline Voice Detection**:
  - Automatically queries and enumerates all installed Windows SAPI5 / OneCore speech voices directly from the OS.
  - Automatically adapts if the user installs new voice packs without requiring code edits or app updates.
  - Added direct quick-access button: **"Add / Download More Offline Voices (Windows Settings)"** which opens `ms-settings:speech` directly.
- **Expanded World Languages HD Neural Catalog**:
  - Added top international languages: Spanish (`Alvaro`, `Dalia`), French (`Henri`), German (`Conrad`), Italian (`Diego`), Arabic (`Hamed`), and Japanese (`Keita`), alongside US/UK English and Hebrew.
- **Refined Windows 11 Fluent UI Styling & Mica Hover Effects**:
  - Polished `CTkTabview` segmented buttons with custom deep-slate background and bright cyan active highlights.
  - Updated developer profile bio to feature Windows 11 & Win32 systems engineering alongside Linux Kernel & GNOME development.
- **Single Desktop Shortcut Enforcement & Shell Cache Flush**:
  - Purged all redundant shortcuts (`Read Aloud.lnk`, `FluentVoice Settings.lnk`).
  - Added automated Windows Shell change notification (`SHChangeNotify`) to instantly flush Explorer's desktop icon cache.
- **Automated Security & Dependabot Integration**:
  - Added `.github/dependabot.yml` for automated weekly pip dependency monitoring and security alerts.
  - Enabled GitHub Dependabot vulnerability alerts on the repository.

---

## [1.2.0] - 2026-09-08

### Added
- **Native Windows 11 Dark Mode Menus (`uxtheme[135]` ForceDark)**:
  - Enabled immersive dark mode across all Win32 context menus and popups.
  - Replaced the low-contrast khaki/beige hover highlight with clean dark slate backgrounds and crisp high-contrast selection.
- **Subprocess Settings & About Dispatcher**:
  - Tray menu options now spawn the Settings GUI and Developer Profile via an isolated `subprocess.Popen` call.
  - Eliminates Tkinter thread lockups and guarantees the Control Center opens instantly on top.
- **Single Unified Desktop Icon**:
  - Consolidated desktop shortcuts into a single official **`FluentVoice Pro`** shortcut.
  - Double-clicking opens the full Voice & Speech Control Center.
- **Expanded Multilingual Voice Library (English, Hebrew & Offline)**:
  - Added studio-grade English neural voices (`Jenny`, `Guy`, `Ryan`, `Sonia`).
  - Added native Hebrew neural voices (`Avri`, `Hila`) for fluent Hebrew speech synthesis.
  - Preserved instant 0ms offline local Windows voices (`Zira`, `Hazel`) for network fail-safe operation.
- **Windows 11 Immersive Dark Title Bar**:
  - Injected `DWMWA_USE_IMMERSIVE_DARK_MODE` and caption color (`#101622`) to eliminate the bright green system title bar accent.
- **Real-Time Speech Speed Synchronization**:
  - GUI speed slider dynamically calculates `rate="+X%"` / `rate="-X%"` and binds directly into the Edge TTS engine.

---

## [1.1.0] - 2026-09-08

### Added
- **Windows 11 Fluent Settings & Control Center GUI (`fluentvoice.gui`)**:
  - Dark-mode interface built with CustomTkinter.
  - Interactive voice profile dropdown selector.
  - Speech speed / pace slider (0.6x to 1.6x) with real-time feedback.
  - Voice test sandbox with live synthesis testing and stop controls.
  - Automation toggles for "Auto-Read on Copy" and "AI Markdown Cleaner".
  - Dedicated "About & Developer" tab with maintainer credits, email, open-source portfolio, and direct PayPal support button.
- **Redesigned Ultra-Crisp Tray Icon**:
  - Re-engineered system tray icon (`tray_icon.png` / `tray_icon.ico`) with transparent background and high-contrast neon cyan glyph.
  - Completely eliminates the clamped/wrinkled margins at 16x16, 20x20, 24x24, and 32x32 system tray scales.
- **Dedicated Desktop Shortcuts**:
  - `FluentVoice Pro.lnk`: 1-Click Speak / Stop toggle.
  - `FluentVoice Settings.lnk`: Instant launch of the Fluent Control Center GUI.
- **Enhanced System Tray Context Menu**:
  - Added direct links to Settings & Control Center, About & Developer Credits, PayPal Donation, and GitHub Repository.
  - Re-organized submenus for Neural voices and Offline local voices.
- **Dual CLI Dispatcher**:
  - `fluentvoice --gui` opens the Control Center directly.
  - `fluentvoice --about` opens the developer profile and credits directly.

---

## [1.0.0] - 2026-09-08

### Added
- **Single-Stream Audio Engine**: Atomic generation tracking (`current_generation_id`) to completely eliminate overlapping or colliding voices during rapid triggers.
- **Ultra HD Neural Voice Engine**: High-definition cloud neural voices (`Andrew`, `Ava`, `Brian`, `Emma`) with lifelike pacing and cadence.
- **Instant Offline Windows SAPI/OneCore Engine**: Automatic fallback to local native voices (`Zira`, `Hazel`) for 0ms response latency without internet connection.
- **AI & Markdown Cleaner**: Intelligent filter stripping code blocks (` ``` `), backticks, links, headers, and asterisks for smooth reading.
- **Windows 11 Fluent Tray Suite**: Modern system tray daemon with single-instance mutex (`NickOtmazgin_FluentVoicePro_SingleInstance_Mutex`), left-click toggle, voice switcher, and auto-read on copy.
- **Debounced Clipboard Watcher**: Smart 0.8s debounce monitor to prevent duplicate triggers while copying.
- **One-Click Installation**: Automated installer script (`install.ps1`) for desktop shortcuts, taskbar pinning, startup persistence, and explorer context menus.
- **Modern 2026 Visual Identity**: Custom Fluent squircle icon in cyber cyan and dark mica gradient.
