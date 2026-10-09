# Microsoft Store listing — FluentVoice Pro

Text for Partner Center (product **9N293MJ0MD9F**). Update it here first, then paste it in, so the listing and the repo stay in sync.

**Live:** https://apps.microsoft.com/detail/9N293MJ0MD9F since 2026-10-09 (1.6.0; 1.6.1 submitted the same day). IARC Global Rating ID 039b0d55-5718-89b9-8d30-3fa5382f3719 (3+ / Everyone).

**Each update submission:** upload the release's `FluentVoicePro-<ver>-x64.msix` (test it locally first, see AGENTS.md), keep Properties → Product declarations → "allows users to make purchases, but does not use the Microsoft Store commerce system" **ticked** (PayPal donate link, policy 10.8.2) and "record and broadcast clips" unticked (Games only), and fill "What's new".

## Product name
FluentVoice Pro

## Short description (≤ 100 characters)
Read any text aloud from the tray, with natural online and offline voices.

## Description
FluentVoice Pro reads text aloud for you, from anywhere in Windows. Select or copy text in any app and press a hotkey (Ctrl+Shift+Space by default), click the tray icon, or turn on Auto-Read on Copy.

Choose the voice that suits you:
• Natural Microsoft online voices in 22 languages.
• Offline HD voices (Piper and Kokoro) that run entirely on your PC. You download only the ones you want; every file is checked against a fixed SHA-256 fingerprint, and each voice shows its licence.
• The voices built into Windows.

Privacy first: switch on "Offline only" and nothing you read is ever sent to the internet. Text that looks like a password or an API key is never read aloud. There are no accounts, no ads and no tracking.

Also included: a Direct Text Reader window for long texts, automatic language detection with a preferred voice for each language, speed, pitch and volume controls, a clean-up for text copied from PDFs, and a dark Fluent-style Settings window.

FluentVoice Pro is free and open source (MIT): https://github.com/nickotmazgin/fluentvoice-pro

About the online voices: they are Microsoft Edge's Read Aloud voices, reached through the open-source edge-tts library. This is not an official Microsoft service for other apps and is meant for personal reading; Microsoft may change or stop it at any time, in which case FluentVoice Pro continues with offline voices.

## What's new in this version
1.6.1 (submitted 2026-10-09): Settings now matches the Store version. The Start with Windows note points to Windows Settings > Apps > Startup, updates come from the Microsoft Store, and options that only apply to the GitHub download are hidden. Small fixes to the release packages.

1.6.0 (first release): left blank, as Partner Center asks for a first submission.

## Product features (one per line, ≤ 200 characters each)
- Reads selected or copied text aloud with a global hotkey or from the tray
- Natural Microsoft online voices in 22 languages
- 57 offline HD voices (Piper and Kokoro) that run on your PC, SHA-256 verified
- Offline-only privacy mode: no text ever leaves your computer
- Automatic language detection with a preferred voice per language
- Direct Text Reader for long texts, with speed, pitch and volume
- Never reads passwords or API keys aloud
- Free and open source (MIT), no ads, no account, no tracking

## Search terms (up to 7)
text to speech, read aloud, TTS, screen reader, accessibility, offline voices, voice reader

## Category
Productivity (subcategory, if asked: none). Secondary idea: Utilities & tools.

## URLs
- Website: https://github.com/nickotmazgin/fluentvoice-pro
- Support: https://github.com/nickotmazgin/fluentvoice-pro/issues
- Privacy policy: https://github.com/nickotmazgin/fluentvoice-pro/blob/main/PRIVACY.md

## Copyright and trademark
© 2026 Nick Otmazgin. FluentVoice Pro is open source under the MIT License.

## Screenshots (desktop, at least 1366×768; ours are 1920×1140)
From `screenshots/v1.6.1/`, in this order: 01 Reader, 03 Voice Providers, 06 tray menu, 02 Voice & Speech, 04 Automation, 10 Voice Providers (Piper), 11 Voice Providers (Kokoro & rights), 12 Automation (tray & startup), 05 About.
Store logo: Partner Center can use the package logo; a 300×300 PNG can be made from `assets/icon.png` if asked.

## Pricing and availability
Free. All markets. Visibility: public.

## Age rating (IARC questionnaire)
Utility app, no user-generated content shared with others, no purchases, no location, no ads → expected rating 3+ / Everyone.

## Notes for certification
FluentVoice Pro is a system-tray app: after launch it lives in the notification area (near the clock). Open Settings by clicking FluentVoice Pro in the Start menu again or from the tray menu. Online voices need an internet connection; offline voices can be downloaded in Settings → Voice Providers (data files from Hugging Face and GitHub, verified by SHA-256; no executable code is downloaded). No account or sign-in is needed.
