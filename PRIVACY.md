# Privacy — FluentVoice Pro

FluentVoice Pro is a **local Windows** TTS / read-aloud suite. It does **not** collect accounts, analytics, or sell personal data.

## What stays on your computer

- Settings in your user config (voice, rate, pitch, volume, hotkey, preferred voices, toggles)
- Optional clipboard text when **Auto-Read on Copy** is enabled (processed locally to speak)
- Temporary audio used for playback (not uploaded by FluentVoice except as required by the TTS engine you choose)

## Network

- **Online HD voices (Microsoft, via edge-tts):** outbound HTTPS to Microsoft speech endpoints with the text you ask to speak
- **Offline HD voices (Piper / Kokoro):** speech is created on your PC; no text is sent anywhere. Downloading a voice (only when you click **Download** in Settings → Voice Providers) fetches the voice files from the official Piper voice library on Hugging Face or the official sherpa-onnx release on GitHub; every file is checked against a fixed SHA-256 fingerprint
- **Offline Windows voices (SAPI / OneCore):** no network required for synthesis
- **Privacy mode ("Offline only", Settings → Voice Providers or the tray menu):** no text is ever sent to an online voice; offline HD or Windows voices read everything
- **Passwords and keys** copied to the clipboard (or marked private by a password manager) are never read aloud or sent anywhere, with any voice
- **Update check (optional, on by default):** one anonymous HTTPS GET to the public GitHub Releases API (`api.github.com/repos/nickotmazgin/fluentvoice-pro/releases/latest`) at most once a day, or when you click **Check for Updates**. No identifiers are sent. Turn it off in Settings → About & Developer → Updates.
- **Microsoft Store version:** there is no GitHub update check at all; the Microsoft Store delivers updates, and Windows manages Start with Windows (Settings → Apps → Startup)
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
