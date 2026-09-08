# Changelog

All notable changes to **FluentVoice Pro** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
