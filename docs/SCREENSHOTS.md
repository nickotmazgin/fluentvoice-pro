# Screenshots (v1.4.18)

HD captures for the README, the GitHub social preview, and social posts.

## Repo paths

| File | Purpose |
|------|---------|
| `screenshots/v1.4.18/collage-v1.4.18.jpg` | README hero collage (3840 wide, 3×2) |
| `screenshots/v1.4.18/social-preview-1280x640.jpg` | GitHub OG / link preview (also `.github/social-preview.{jpg,png}`) |
| `screenshots/v1.4.18/social-collage-1080.jpg` | Square social post |
| `screenshots/v1.4.18/01-settings-reader.png` | 01 Direct Text Reader |
| `screenshots/v1.4.18/02-settings-voice.png` | 02 Voice & Speech |
| `screenshots/v1.4.18/03-settings-automation.png` | 03 Automation & System (Auto-Read, language, hotkey) |
| `screenshots/v1.4.18/04-settings-about-updates.png` | 04 About · Updates & Factory Reset |
| `screenshots/v1.4.18/05-tray-menu.png` | 05 Tray right-click menu |
| `screenshots/v1.4.18/06-desktop-icon-live.png` | 06 Desktop icon |
| `screenshots/v1.4.18/07-tray-icon-closeup.png` | 07 Tray icon near the clock |
| `screenshots/v1.4.18/08-settings-automation-updates.png` | 08 Automation · tray daemon & Updates |

## Rebuild the collages

Drop new captures into `screenshots/v<version>/` with the file names above, then:

```powershell
python scriptsuild_collage.py
```

The version is read from `fluentvoice/__init__.py`. The GitHub social preview image must be uploaded
by hand under **Settings → General → Social preview** (GitHub has no API for it).
