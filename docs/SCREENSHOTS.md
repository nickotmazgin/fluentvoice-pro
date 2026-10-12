# Screenshots (v1.6.3)

HD captures for the README, the GitHub social preview, and social posts. In v1.6.3 every Settings
screen was recaptured (the header shows the version; 08's tip mentions Multilingual reading of other
languages) and 13–15 are new: the health check, a Dutch text in the Reader, and the bottom of About
& Developer. The tray captures 06, 07 and 09 are unchanged from v1.6.1.

## Repo paths

| File | Purpose |
|------|---------|
| `screenshots/v1.6.3/collage-v1.6.3.jpg` | README hero collage (3840 wide, 3 across: 01–06, 13, 08–12) |
| `screenshots/v1.6.3/social-preview-1280x640.jpg` | GitHub OG / link preview: the full collage, 4 across (also `.github/social-preview.{jpg,png}`) |
| `screenshots/v1.6.3/social-collage-1080.jpg` | Square social post (03, 13, 06, 01) |
| `screenshots/v1.6.3/01-settings-reader.png` | 01 Direct Text Reader |
| `screenshots/v1.6.3/02-settings-voice.png` | 02 Voice & Speech |
| `screenshots/v1.6.3/03-settings-voice-providers.png` | 03 Voice Providers: privacy, rights, Piper / Kokoro downloads |
| `screenshots/v1.6.3/04-settings-automation.png` | 04 Automation & System (Auto-Read, language, Global Hotkey with Stop-only chord and read-selection switch, notifications) |
| `screenshots/v1.6.3/05-settings-about-updates.png` | 05 About · Updates and the start of Components & sources |
| `screenshots/v1.6.3/06-tray-menu.png` | 06 Tray right-click menu (Offline HD Voices submenu open, languages of the downloaded voices) |
| `screenshots/v1.6.3/07-tray-icon-closeup.png` | 07 Tray icon: HD (drawn by the tray code) + live 20 px capture from the taskbar (README only) |
| `screenshots/v1.6.3/08-settings-automation-preferred.png` | 08 Automation scrolled to Preferred Voices (one Language ▸ Voice row), tray, startup |
| `screenshots/v1.6.3/09-tray-offline-voices.png` | 09 Tray → Offline HD Voices → English: the downloaded Piper / Kokoro voices |
| `screenshots/v1.6.3/10-settings-voice-providers-mid.png` | 10 Voice Providers, middle: Piper voices, each with its licence |
| `screenshots/v1.6.3/11-settings-voice-providers-bottom.png` | 11 Voice Providers, bottom: Kokoro pack, Windows voices, licences & rights |
| `screenshots/v1.6.3/12-settings-automation-bottom.png` | 12 Automation & System, bottom: tray, startup & shortcuts, updates, how to trigger FluentVoice |
| `screenshots/v1.6.3/13-settings-health-check.png` | 13 About → Components & sources after **Test providers**: diagnosis and fixes |
| `screenshots/v1.6.3/14-reader-other-language.png` | 14 Reader with Dutch text: "Lang: Dutch (Multilingual voice)" (README only) |
| `screenshots/v1.6.3/15-settings-about-bottom.png` | 15 About, bottom: component versions, licences and sources, Advanced (factory reset) (README only) |

## Recapture + rebuild

```powershell
python scripts\capture_settings.py   # 01–05, 10–12 (maximized Settings tabs, temporary profile)
python scripts\capture_settings.py --at screenshots\v<ver>\08-settings-automation-preferred.png "Automation & System" 0.6
python scripts\capture_settings.py --at screenshots\v<ver>\15-settings-about-bottom.png "About & Developer" 1.0
python scripts\build_collage.py      # collage + social images
```

13 (About scrolled to 0.6, Test providers pressed, report shown after ~12 s) and 14 (Dutch text pasted
into the Reader) are taken the same way with a temporary profile. 06 and 09 (tray menu, captured with a
tray running on a temporary profile that has offline voices) and 07 (tray icon) are captured by hand
into the same folder with the names above.

The version is read from `fluentvoice/__init__.py`. The GitHub social preview image must be uploaded
by hand under **Settings → General → Social preview** (GitHub has no API for it).
