# Privacy — FluentVoice Pro

FluentVoice Pro is a **local Windows** TTS / read-aloud suite. It does **not** collect accounts, analytics, or sell personal data.

## What stays on your computer

- Settings in your user config (voice, rate, pitch, volume, hotkey, preferred voices, toggles)
- Optional clipboard text when **Auto-Read on Copy** is enabled (processed locally to speak)
- Temporary audio used for playback (not uploaded by FluentVoice except as required by the TTS engine you choose)

## Network

- **Online neural voices (Edge TTS):** outbound HTTPS to Microsoft speech endpoints with the text you ask to speak
- **Offline SAPI / OneCore:** no network required for synthesis
- Donate / GitHub / PayPal links open **only when you click them**

FluentVoice does **not** embed advertising SDKs or third-party trackers.

## What we do not do

- No telemetry or crash phoning home from this app
- No cloud sync or FluentVoice account
- No reading your files except what you paste into the Reader or what Auto-Read takes from the clipboard when enabled

## Contact

Privacy questions: [nickotmazgin.dev@gmail.com](mailto:nickotmazgin.dev@gmail.com) or [GitHub Security](https://github.com/nickotmazgin/fluentvoice-pro/security).

See also [`docs/WINDOWS_TRUST.md`](docs/WINDOWS_TRUST.md) and [`SECURITY.md`](SECURITY.md).

MIT License — see [LICENSE](LICENSE).
