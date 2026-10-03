# AGENTS.md — guide for AI coding assistants (Claude Code, Cursor, …)

FluentVoice Pro is a Windows 10/11 tray text-to-speech app in Python (3.10–3.14).

## Layout
- `fluentvoice/` — the app: `tray.py` (tray daemon), `gui.py` (Settings window), `core.py` (speech plan, fallback), `voices.py` (voice catalogue), `localtts.py` + `local_catalog.py` (offline Piper / Kokoro voices), `updater.py`, `lifecycle.py`, `config.py`.
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
- Release: merge the PR, then a signed tag `vX.Y.Z` triggers `release-publish.yml` (attested ZIPs + `SHA256SUMS.txt`). Only the latest release is kept published; old tags stay.
- Every offline voice file is pinned by SHA-256 and size in `local_catalog.py`; downloads are allowed only from the official hosts listed in `localtts.py`. Never loosen these checks.
- GitHub Actions are pinned to full commit SHAs with the version in a comment; let Dependabot bump them.
- Voice licences: only add voices whose licence allows it, and record it in `docs/VOICE_LICENSES.md` (`scripts/gen_voice_licenses.py`). No "fair use" claims; the Microsoft online voices are for personal use (see README legal section).
- Tests and screenshot or demo scripts must use a throwaway profile (temporary `HOME` / `APP_DIR`), never the developer's real settings or clipboard.
- Public media (screenshots, videos) must not show the desktop, the Windows username or personal files.
- Discussion and README images must link to a commit SHA (`raw.githubusercontent.com/.../<sha>/...`), not `main`, because old screenshot folders are removed.
- No secrets, tokens or personal paths in commits. Keep diffs small and focused; update `CHANGELOG.md` for user-visible changes.
