# Changelog

All notable changes to **FluentVoice Pro** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] - 2026-09-08

### Added
- **Native Windows Toast & Popup Notification System**:
  - Live toast / balloon alerts for key actions: Auto-Read on Copy (Enabled/Disabled), voice switching with voice name, active speech playback with text snippet preview, and instant playback stop.
  - Full user toggle switch in **Settings -> Automation & System**: easily turn Windows notifications on or off.
- **Dynamic Local Offline Voice Detection**:
  - Automatically queries and enumerates all installed Windows SAPI5 / OneCore speech voices directly from the OS.
  - Automatically adapts if the user installs new voice packs without requiring code edits or app updates.
  - Added direct quick-access button: **"Add / Download More Offline Voices (Windows Settings)"** which opens `ms-settings:speech` directly.
- **Expanded World Languages HD Neural Catalog**:
  - Added top international languages: Spanish (`Alvaro`, `Dalia`), French (`Henri`), German (`Conrad`), Italian (`Diego`), Arabic (`Hamed`), and Japanese (`Keita`), alongside US/UK English and Hebrew.
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
