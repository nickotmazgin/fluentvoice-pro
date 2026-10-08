# AGENTS.md — guide for AI coding assistants (Claude Code, Cursor, …)

FluentVoice Pro is a Windows 10/11 tray text-to-speech app in Python (3.10–3.14).

## Layout
- `fluentvoice/` — the app: `tray.py` (tray daemon), `gui.py` (Settings window), `core.py` (speech plan, fallback), `voices.py` (voice catalogue), `localtts.py` + `local_catalog.py` (offline Piper / Kokoro voices), `updater.py`, `lifecycle.py`, `config.py`.
- `fluentvoice/msix.py` — Microsoft Store (MSIX) detection; `packaging/AppxManifest.xml.in` + `scripts/make_msix_layout.py` + `scripts/build_msix.ps1` build the Store package (CI only: needs the Windows SDK). In the Store build the GitHub updater, Startup shortcut and custom app identity are off.
- `tests/` — pytest suite; `scripts/` — build, release ZIPs, screenshots, collage; `docs/` — user docs.

## Commands
```powershell
python -m pip install -r requirements.txt pytest
python -m pytest -q                 # must pass before any PR
python -m fluentvoice.tray          # run the tray
python -m fluentvoice.cli --gui     # Settings window
```

## Rules
- `main` is protected: work on a branch, open a PR, the checks `Tests (Python 3.10/3.12/3.14)` must pass, squash merge only. Never force-push or push to `main` directly.
- Version lives in three places that must match: `fluentvoice/__init__.py`, `pyproject.toml`, `CHANGELOG.md`.
- Release: merge the PR, then a signed tag `vX.Y.Z` triggers `release-publish.yml` (attested source ZIP, portable ZIP, Store MSIX + `SHA256SUMS.txt`). Keep every release published: winget and Scoop manifests link to a specific version's assets, so deleting a release breaks them. Prune only releases older than a year that no package manifest still points to.
- Every offline voice file is pinned by SHA-256 and size in `local_catalog.py`; downloads are allowed only from the official hosts listed in `localtts.py`. Never loosen these checks.
- GitHub Actions are pinned to full commit SHAs with the version in a comment; let Dependabot bump them.
- Voice licences: only add voices whose licence allows it, and record it in `docs/VOICE_LICENSES.md` (`scripts/gen_voice_licenses.py`). No "fair use" claims; the Microsoft online voices are for personal use (see README legal section).
- Tests and screenshot or demo scripts must use a throwaway profile (temporary `HOME` / `APP_DIR`), never the developer's real settings or clipboard.
- Public media (screenshots, videos) must not show the desktop, the Windows username or personal files.
- Discussion and README images must link to a commit SHA (`raw.githubusercontent.com/.../<sha>/...`), not `main`, because old screenshot folders are removed.
- No secrets, tokens or personal paths in commits. Keep diffs small and focused; update `CHANGELOG.md` for user-visible changes.

## After a release
- **winget** (`NickOtmazgin.FluentVoicePro`): PR to `microsoft/winget-pkgs` from the fork `nickotmazgin/winget-pkgs` with the new portable ZIP URL and its SHA-256 (uppercase), validated with `winget validate --manifest <dir>`. If a PR is still open, update it instead of opening another.
- **Scoop** (`nickotmazgin/scoop-bucket`, `bucket/fluentvoicepro.json`): `checkver`/`autoupdate` read `SHA256SUMS.txt`; confirm the bucket moved to the new version and `scoop install` works.
- While a winget or Store review is pending, batch fixes into fewer releases: every release restarts the review.

## Microsoft Store
- Never cancel or edit a submission while it is in certification; fixes wait for the next submission.
- Every submission ticks Properties → Product declarations → "allows users to make purchases, but does not use the Microsoft Store commerce system" (the in-app PayPal donate link, Store policy 10.8.2).
- Test an MSIX locally before submitting: turn on Developer Mode, unpack the `.msix`, delete `AppxBlockMap.xml` and `[Content_Types].xml`, `Add-AppxPackage -Register <dir>\AppxManifest.xml`, launch it from Start, then `Remove-AppxPackage` so it can't clash with the Store install. Back up `%USERPROFILE%\.fluentvoice` first: the packaged app uses the real profile.
