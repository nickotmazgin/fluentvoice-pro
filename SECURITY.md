# Security Policy

## Threat model

FluentVoice Pro is a **local Windows 11/10** system-tray TTS suite. It can:

- Read clipboard text (optional Auto-Read) and speak it
- Register a global hotkey
- Call **outbound HTTPS** to Microsoft Edge neural TTS when online voices are used
- Fall back to local **SAPI / OneCore** voices (no network)
- Create desktop / Startup shortcuts and Explorer context-menu entries via the installer

Install only from official [GitHub Releases](https://github.com/nickotmazgin/fluentvoice-pro/releases) (attested ZIP assets) or this repository’s `main` tag.

**Platforms:** Windows **11** and **10** (x64). Python **3.10+** for the source install; portable EXE ZIP needs no Python.

## Supported versions

| Version line | Status |
| --- | --- |
| **v1.4.x** (latest) | Actively supported |
| &lt; 1.4 | Best-effort / upgrade recommended |

## Reporting a vulnerability

**Please do NOT create a public GitHub issue for security vulnerabilities.**

Use one of these private channels:

1. **GitHub → Security → “Report a vulnerability”** (preferred) — private advisory with maintainers.
2. **Email:** [nickotmazgin.dev@gmail.com](mailto:nickotmazgin.dev@gmail.com)  
   Subject: `[SECURITY] FluentVoice Pro - Vulnerability Report`

### What to include

- Clear description and impact
- Steps to reproduce
- Windows version / build, FluentVoice version, install path (source ZIP vs portable)
- Whether neural (online) or offline voices were used
- Relevant logs (avoid pasting clipboard contents or secrets)

## Response & disclosure

- **Acknowledgement:** within **48 hours**
- **Triage:** within **7 days**
- **Fix / mitigation / plan:** within **30 days** for supported lines

We coordinate disclosure with you. Fixes ship in a GitHub Release / Security Advisory when appropriate. Reporters are credited unless you request otherwise.

## Scope

Covers FluentVoice Pro source, release ZIPs, and installer scripts in this repository.  
**Does not** cover Microsoft Edge TTS service, Windows Speech Runtime, Python, or third-party antivirus false positives (see [`docs/WINDOWS_TRUST.md`](docs/WINDOWS_TRUST.md)).

## Safe harbor

We will not pursue legal action against good-faith research that avoids privacy violations, data destruction, and degradation of other users’ systems, and that respects coordinated disclosure.
