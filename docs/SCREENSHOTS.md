# Screenshots (v1.4.19)

HD captures for the README, the GitHub social preview, and social posts.

## Repo paths

| File | Purpose |
|------|---------|
| `screenshots/v1.4.19/collage-v1.4.19.jpg` | README hero collage (3840 wide, 3×3: 01–09) |
| `screenshots/v1.4.19/social-preview-1280x640.jpg` | GitHub OG / link preview (also `.github/social-preview.{jpg,png}`) |
| `screenshots/v1.4.19/social-collage-1080.jpg` | Square social post |
| `screenshots/v1.4.19/01-settings-reader.png` | 01 Direct Text Reader |
| `screenshots/v1.4.19/02-settings-voice.png` | 02 Voice & Speech |
| `screenshots/v1.4.19/03-settings-automation.png` | 03 Automation & System (Auto-Read, language, hotkey) |
| `screenshots/v1.4.19/04-settings-about-updates.png` | 04 About · Updates & Factory Reset |
| `screenshots/v1.4.19/05-tray-menu.png` | 05 Tray right-click menu |
| `screenshots/v1.4.19/06-desktop-icon-live.png` | 06 Desktop icon |
| `screenshots/v1.4.19/07-tray-icon-closeup.png` | 07 Tray icon near the clock |
| `screenshots/v1.4.19/08-settings-automation-updates.png` | 08 Automation · Startup & Shortcuts, tray daemon, Updates |
| `screenshots/v1.4.19/09-portable-first-launch.png` | 09 Portable EXE first-launch prompt (Start with Windows?) |

## Recapture + rebuild

```powershell
python scripts\capture_settings.py   # 01–04 (maximized Settings tabs, temporary profile)
python scripts\build_collage.py      # collage + social images
```

05 (tray menu), 06/07 (icons), 08 (Automation bottom: `capture_settings.py --bottom <png>`) and
09 (portable first-launch prompt) are captured by hand into the same folder with the names above.

The version is read from `fluentvoice/__init__.py`. The GitHub social preview image must be uploaded
by hand under **Settings → General → Social preview** (GitHub has no API for it).
