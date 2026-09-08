# Changelog

All notable changes to **FluentVoice Pro** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
