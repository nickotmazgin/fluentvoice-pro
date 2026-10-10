# Screenshots (v1.6.2)

HD captures for the README, the GitHub social preview, and social posts. In v1.6.2 only 04 was
recaptured (the Global Hotkey card gained the Stop-only chord and the read-selection switch); the
other panels are the v1.6.1 captures.

## Repo paths

| File | Purpose |
|------|---------|
| `screenshots/v1.6.2/collage-v1.6.2.jpg` | README hero collage (3840 wide, 3 across: 01–12) |
| `screenshots/v1.6.2/social-preview-1280x640.jpg` | GitHub OG / link preview: the full collage, 4 across (also `.github/social-preview.{jpg,png}`) |
| `screenshots/v1.6.2/social-collage-1080.jpg` | Square social post |
| `screenshots/v1.6.2/01-settings-reader.png` | 01 Direct Text Reader |
| `screenshots/v1.6.2/02-settings-voice.png` | 02 Voice & Speech |
| `screenshots/v1.6.2/03-settings-voice-providers.png` | 03 Voice Providers: privacy, rights, Piper / Kokoro downloads |
| `screenshots/v1.6.2/04-settings-automation.png` | 04 Automation & System (Auto-Read, language, Global Hotkey with Stop-only chord and read-selection switch, notifications) |
| `screenshots/v1.6.2/05-settings-about-updates.png` | 05 About · Updates & Factory Reset |
| `screenshots/v1.6.2/06-tray-menu.png` | 06 Tray right-click menu (Offline HD Voices submenu open, languages of the downloaded voices) |
| `screenshots/v1.6.2/07-tray-icon-closeup.png` | 07 Tray icon: HD (drawn by the tray code) + live 20 px capture from the taskbar |
| `screenshots/v1.6.2/08-settings-automation-preferred.png` | 08 Automation scrolled to Preferred Voices (one Language ▸ Voice row), tray, startup, updates |
| `screenshots/v1.6.2/10-settings-voice-providers-mid.png` | 10 Voice Providers, middle: Piper voices, each with its licence |
| `screenshots/v1.6.2/11-settings-voice-providers-bottom.png` | 11 Voice Providers, bottom: Kokoro pack, Windows voices, licences & rights |
| `screenshots/v1.6.2/12-settings-automation-bottom.png` | 12 Automation & System, bottom: tray, startup & shortcuts, updates, how to trigger FluentVoice |
| `screenshots/v1.6.2/09-tray-offline-voices.png` | 09 Tray → Offline HD Voices → English: the downloaded Piper / Kokoro voices (README only, not in the collage) |

## Recapture + rebuild

```powershell
python scripts\capture_settings.py   # 01–05, 10–12 (maximized Settings tabs, temporary profile)
python scripts\build_collage.py      # collage + social images
```

06 and 13 (tray menu, captured with a tray running on a temporary profile that has offline voices), 07 (tray icon), 08 (Automation scrolled to Preferred Voices) and 09 (portable
first-launch prompt) are captured by hand into the same folder with the names above.

The version is read from `fluentvoice/__init__.py`. The GitHub social preview image must be uploaded
by hand under **Settings → General → Social preview** (GitHub has no API for it).
