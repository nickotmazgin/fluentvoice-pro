# FluentVoice Pro — Windows trust, SmartScreen, App Control & firewall

This release ships **two download options** from GitHub Releases (both can carry green **Artifact Attestation** stamps when built by Actions):

| Asset | Who it’s for | Notes |
| --- | --- | --- |
| `fluentvoice-pro-<ver>-windows.zip` | **Recommended** | Source + `install.ps1` (needs Python 3.10+) |
| `FluentVoicePro-<ver>-portable-win64.zip` | No Python | PyInstaller folder with `FluentVoicePro.exe` |

## Green checkmarks on GitHub Releases

Those stamps are **GitHub Artifact Attestations** (Sigstore provenance): the ZIP was built from this repository’s tagged commit by GitHub Actions. They are **not** the same as a paid Windows Authenticode signature.

## SmartScreen / “Windows protected your PC”

Unsigned desktop binaries may show SmartScreen the first time. That is normal without a purchased code-signing certificate.

**Mitigations we use (no paid cert required):**

1. Prefer the **source ZIP + install.ps1** path (Python) when possible.
2. Ship the portable build as a **ZIP**, not a lone `.exe` upload.
3. Publish via **Actions + attestations** so Releases show green verification.
4. Clear Unblock / Run anyway steps below.

**What we do *not* do:** self-signed Authenticode. It does **not** satisfy SmartScreen and often adds friction.

Paid Authenticode (EV/OV) is optional later if SmartScreen becomes a frequent support burden.

### Unblock a downloaded file (MOTW)

```powershell
Unblock-File .\install.ps1
# or for portable:
Unblock-File .\FluentVoicePro.exe
```

Or: file Properties → check **Unblock** → Apply.

SmartScreen dialog: **More info** → **Run anyway**.

### PowerShell execution policy

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

## Windows Firewall

FluentVoice Pro does **not** open inbound ports and does **not** install a firewall rule.

- **Outbound HTTPS** to Microsoft Edge neural TTS endpoints when online voices are used.
- Offline SAPI/OneCore voices need no network.

Default Windows Firewall allows user-initiated outbound HTTPS. No manual firewall change is required for normal use.

## Smart App Control / WDAC / enterprise allowlisting

On locked-down PCs:

- Allowlist the install folder or `FluentVoicePro.exe`.
- Or run the Python install path if your org already trusts `pythonw.exe`.

## App Control / Defender false positives

If Defender quarantines a fresh PyInstaller build (rare packer heuristic):

1. Confirm the file SHA matches the GitHub Release attestation.
2. Restore from quarantine / add an exclusion for the extract folder.
3. Prefer the source ZIP install if corporate policy blocks unsigned packagers.

## Recommended install order

1. Download **source ZIP** from Releases (attested).
2. Unblock + run `install.ps1`.
3. Confirm tray icon; run `docs/SMOKE_TEST.md`.

Portable EXE ZIP is the second option when Python cannot be installed.
