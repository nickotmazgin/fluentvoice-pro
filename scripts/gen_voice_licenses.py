"""Write docs/VOICE_LICENSES.md from fluentvoice/local_catalog.py (tests check it stays in sync).

Usage (repo root):  python scripts/gen_voice_licenses.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fluentvoice import local_catalog as cat, localtts, voices  # noqa: E402

OUT = ROOT / "docs" / "VOICE_LICENSES.md"


def render() -> str:
    lines = [
        "# Offline HD Voice Licences",
        "",
        "Generated from `fluentvoice/local_catalog.py` by `scripts/gen_voice_licenses.py`.",
        "",
        "Offline HD voices are **not bundled** with FluentVoice Pro. You download the ones you want in",
        "**Settings → Voice Providers**, from the official Piper voice library (Hugging Face) or the official",
        "sherpa-onnx release (GitHub). Every file is checked against the SHA-256 fingerprint listed in",
        "`fluentvoice/local_catalog.py` before it is used.",
        "",
        "- ✅ **Free to use**: public domain, CC0, CC BY, CC BY-SA, Apache-2.0 or the Unlicense. CC BY and",
        "  CC BY-SA ask that you credit the source (the link below) if you share audio made with the voice.",
        "- 🏠 **Personal use only**: non-commercial licences, or recordings whose licence the author did not",
        "  state. Fine for reading text to yourself; not for publishing, broadcasting or selling the audio.",
        "",
        "Left out on purpose: voices trained on research-only recordings (for example Ryan, Lessac,",
        "HiFi-Captain, L2-ARCTIC, SEMAINE) and Kokoro voices named after other companies' voices",
        "(OpenAI, Google, Microsoft).",
        "",
        "## Piper voices",
        "",
        f"Engine: [Piper]({cat.PIPER_HOME}) · Voices: [rhasspy/piper-voices]({cat.PIPER_VOICES_HOME})",
        "",
        "| Voice | Language | Use | Licence of the recordings | Source |",
        "| :--- | :--- | :---: | :--- | :--- |",
    ]
    for v in localtts.VOICES:
        if v["provider"] != "piper":
            continue
        use = "✅ Free" if v["kind"] == "free" else "🏠 Personal"
        lang = voices.LANGUAGES[v["family"]] + (f" ({v['region']})" if v["region"] else "")
        lines.append(f"| {v['name']} {('· ' + v['gender']) if v['gender'] else ''} | {lang} | {use} | "
                     f"{v['licence']} | <{v['source']}> |")
    lines += [
        "",
        "## Kokoro voices",
        "",
        f"Model: [Kokoro-82M]({cat.KOKORO_HOME}) v1.0, **Apache-2.0** (✅ free to use) · Pack: "
        f"`{cat.KOKORO_PACK['folder']}` from the official sherpa-onnx release (350 MB, one download for all).",
        "",
        "| Voice | Language |",
        "| :--- | :--- |",
    ]
    for v in localtts.VOICES:
        if v["provider"] == "kokoro":
            lang = voices.LANGUAGES[v["family"]] + (f" ({v['region']})" if v["region"] else "")
            lines.append(f"| {v['name']} · {v['gender']} | {lang} |")
    lines += [
        "",
        "Licence information was checked on each voice's model card in October 2026. If you believe a",
        "listing is wrong, please open an issue and the voice will be corrected or removed.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    print("wrote", OUT)
