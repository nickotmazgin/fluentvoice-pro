# FluentVoice Pro — 2-minute smoke checklist

Use after install or before cutting a release.

1. **Install / launch tray**
   - Run installer or Startup: tray icon appears near the clock.
   - Confirm the Startup shortcut `FluentVoice Pro Tray.lnk` targets `pythonw -m fluentvoice.tray` (portable: `FluentVoicePro.exe`); no `.vbs` launcher since v1.4.19.

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
   - Global hotkey (default `Ctrl+Shift+Space`) toggles speak/stop. Select a sentence in Notepad and press it: the selection is read (Auto-Read on doesn't read it twice); in Windows Terminal it copies with Ctrl+Insert, never Ctrl+C. A chord without a modifier (e.g. `space`) is refused in Settings; a chord another app owns shows "⚠ … already used by another app".
   - Optional Stop hotkey (e.g. `ctrl+shift+x`) only stops.
   - With the internet off (or the online service failing): the reading continues with an offline voice of the text's language after a retry, the next reading starts offline at once, and Hebrew / Thai text with no voice for that language shows what to install instead of staying silent.
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

9. **Voices & auto-route (v1.4.20+)**
   - Voice & Speech: Language = Hebrew, Voice = Avri → the test box shows a right-aligned Hebrew sample → **Speak Test Text** plays Avri.
   - Direct Text Reader with Avri + English text → status shows `auto-routed for English text (your voice: Avri)`.
   - Ava Multilingual + a long Spanish paragraph → still Ava (no routing).
   - Automation & System → Preferred Voices: pick any of the 22 languages in the Language ▸ Voice row; tray → Online HD Voices: World (Microsoft) has a submenu per language.

10. **Notifications, offline voices, clicks (v1.4.22+)**
   - Tray → Voice → pick a voice: the toast header says **FluentVoice Pro** with the app icon (not "Python").
   - Settings → Automation & System → Windows notifications = Important only: reading text shows no "Speaking…" toast; switching to All shows it.
   - Tray → Local Windows Voices (Offline) lists every installed voice (e.g. George / Susan / Hazel UK) and they speak.
   - Double-click the tray icon: speech starts once (does not start-and-stop). Click again while it is preparing: it stops.

11. **Long reads, Auto-Read, mid-read changes (v1.4.25+)**
   - Turn on Auto-Read on Copy and copy a long article (2,000+ characters): it reads straight through with no long pauses.
   - While it reads, pick another voice in the tray: it continues from the current sentence in the new voice. Change the volume in Settings: the playing audio follows.
   - Copy the same text again after it finished: it is read again. Copy it again while it is still being read: it is not restarted.
   - Pick an offline voice (e.g. Windows George): it reads in that voice, and Stop / a tray click stops it at once.
   - Voice & Speech → Language: Hindi, Thai, Tamil… show their voices; the test sentence displays correctly and is spoken in that language.

12. **Private clipboard + Icelandic (v1.4.28+)**
   - Copy a password-like string (e.g. `Tr0ub4dor&3`) and click the tray icon / press the hotkey: "🔒 Skipped private text", nothing is spoken. With Auto-Read on, copying it stays silent.
   - Copy a normal sentence: it is read as usual.
   - Voice & Speech → Language: Icelandic shows Gunnar and Gudrun; the test sentence is spoken in Icelandic.

## v1.5.0 — offline HD voices & privacy mode

13. Settings → **Voice Providers**: Piper → Language *English* → **Download** Joe (63 MB) → progress, then "downloaded, verified and ready". **▶ Try** speaks offline. The voice appears in Voice & Speech → English and in the tray → Offline HD Voices within 2 s.
14. Turn on **Offline only** (Voice Providers or tray). With an online voice selected, Speak Test Text reads with an offline voice (status shows "offline HD, on this PC" or "offline Windows voice"). Turn it off again.
15. Unplug the network with an online voice selected and Joe downloaded: reading continues with Joe ("First voice unavailable → finished with an offline HD voice").
16. **Remove** Joe: it disappears from every list; a reading that used it falls back to a working voice.
