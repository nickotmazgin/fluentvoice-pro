# FluentVoice Pro — 2-minute smoke checklist

Use after install or before cutting a release.

1. **Install / launch tray**
   - Run installer or Startup: tray icon appears near the clock.
   - Confirm Startup shortcut launches `pythonw -m fluentvoice.tray` (via `start_fluentvoice_silent.vbs`).

2. **Tray basics**
   - Left-click tray → speak clipboard / toggle stop.
   - Right-click → dark menu + strong hover contrast (not white / khaki).
   - Open **Direct Text Reader**, paste Hebrew, Speak.

3. **Settings live sync**
   - Open Settings; leave **Automation** tab visible.
   - Toggle **Auto-Read on Copy** from the tray menu → Settings switch updates within ~1s.

4. **Close to Tray revive**
   - Tray → **Exit FluentVoice Pro**.
   - Desktop → open FluentVoice Pro (Settings).
   - Click **Close to Tray** → tray icon returns.
   - Or use Automation → **Ensure Tray Running** / **Restart Tray**.

5. **Offline Voices**
   - Voice & Speech → **Offline Voices (Windows Settings)** opens quickly with status feedback.

6. **Extras (v1.4.3+)**
   - Volume slider changes playback level.
   - Spanish/French sample auto-routes when Smart Language Auto-Routing is on.
   - Preferred Hebrew voice Avri vs Hila applies on Hebrew text.
   - Global hotkey (default `Ctrl+Shift+Space`) toggles speak/stop.
   - Settings tabs (Voice / Automation) show content on first open (not blank).
   - Release assets: try source ZIP install **or** portable EXE ZIP; see `docs/WINDOWS_TRUST.md` if SmartScreen prompts.

7. **Reader streaming + status (v1.4.17+)**
   - Paste a 3,000+ character article into Direct Text Reader → Read Aloud.
   - Audio starts within ~2 s; status shows `🔊 Speaking — <voice> • part i/n • m:ss / m:ss`, then `✔️ Finished`.
   - With Auto-Read on Copy ON, copy text (tray starts reading) then click Read Aloud → tray voice stops, Reader voice takes over (no double voices).
   - Settings **Stop** / **Emergency Stop** also silences tray Auto-Read. Start Menu **Emergency Stop** and **Toggle Speak Stop** work.
   - `%USERPROFILE%\.fluentvoice\speech.log` records any synthesis/playback failure.

8. **Updates (v1.4.17+)**
   - Tray → **Check for Updates…** → toast "up to date" (or popup if newer).
   - Settings → About & Developer → **Check for Updates** → status line updates; toggle auto-check persists.
   - Portable EXE: tray → Settings / Reader / About open (not a second tray).
