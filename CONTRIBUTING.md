# Contributing to FluentVoice Pro

Thanks for helping improve FluentVoice Pro.

## Ways to contribute

1. **Bugs** — [Issues](https://github.com/nickotmazgin/fluentvoice-pro/issues) (use the bug template; search first)
2. **Ideas / Q&A** — [Discussions](https://github.com/nickotmazgin/fluentvoice-pro/discussions)
3. **Features** — discuss first, then a feature-request issue if needed
4. **Docs / screenshots** — README, `docs/`, `screenshots/v1.4.3/`
5. **Code** — bug fixes, tests, packaging (keep PRs focused)

## Security

Do **not** file public issues for vulnerabilities. See [`SECURITY.md`](SECURITY.md).

## Dev setup (Windows)

```powershell
git clone https://github.com/nickotmazgin/fluentvoice-pro.git
cd fluentvoice-pro
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
python -m fluentvoice.tray
```

Settings UI: `python -m fluentvoice.cli --gui`

## Pull requests

- Target `main`
- Run `python -m pytest -q`
- No secrets, tokens, or personal paths in commits
- Prefer small, reviewable diffs
- Update `CHANGELOG.md` for user-visible changes

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
