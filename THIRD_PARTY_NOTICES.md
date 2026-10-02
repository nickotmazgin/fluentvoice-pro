# Third-Party Notices — FluentVoice Pro

FluentVoice Pro's own source code is © 2026 Nick Otmazgin and released under the [MIT License](LICENSE).

FluentVoice Pro uses the open-source components below. The **source ZIP** installs them from PyPI
with `pip`. The **portable EXE** bundles them inside the EXE folder, together with the full texts
of the GPL, LGPL and Apache licences in [`licenses/`](licenses/).

## The portable EXE and the GPL

The portable EXE contains **GPL-3.0** components: the Piper speech engine (`piper-tts`) and the
eSpeak NG pronunciation library it uses. The portable EXE **as a whole** is therefore distributed
under the terms of the [GNU GPL v3](licenses/GPL-3.0.txt). FluentVoice Pro's own code stays under
the MIT License, which is compatible with the GPL.

The complete corresponding source is public:
- FluentVoice Pro: <https://github.com/nickotmazgin/fluentvoice-pro> (the exact tag of each release).
- Every other component: the source links in the table below, at the versions listed in the release.

LGPL components (`edge-tts`, `pystray`) are used as unmodified libraries. You can replace them:
install FluentVoice from the source ZIP and `pip install` any compatible version.

## Components

| Component | Used for | Licence | Source |
| :--- | :--- | :--- | :--- |
| Python & Tcl/Tk | runtime, windows | PSF-2.0 / Tcl/Tk (BSD-style) | <https://www.python.org> |
| edge-tts | Microsoft online voices | LGPL-3.0 (one file MIT) | <https://github.com/rany2/edge-tts> |
| piper-tts | Piper offline HD voices | GPL-3.0-or-later | <https://github.com/OHF-Voice/piper1-gpl> |
| eSpeak NG (inside piper-tts and sherpa-onnx) | pronunciation (phonemes) | GPL-3.0-or-later | <https://github.com/espeak-ng/espeak-ng> |
| Nakdimon (inside piper-tts) | Hebrew vowel marks for the Hebrew Piper voice | MIT | <https://github.com/elazarg/nakdimon> |
| sherpa-onnx | Kokoro offline HD voices | Apache-2.0 | <https://github.com/k2-fsa/sherpa-onnx> |
| ONNX Runtime | runs the offline voice models | MIT | <https://github.com/microsoft/onnxruntime> |
| NumPy | audio samples | BSD-3-Clause | <https://numpy.org> |
| pathvalidate | used by piper-tts | MIT | <https://github.com/thombashi/pathvalidate> |
| flatbuffers, protobuf | used by ONNX Runtime | Apache-2.0 / BSD-3-Clause | <https://github.com/google/flatbuffers>, <https://github.com/protocolbuffers/protobuf> |
| pystray | tray icon | LGPL-3.0 | <https://github.com/moses-palmer/pystray> |
| CustomTkinter | Settings window | MIT | <https://github.com/TomSchimansky/CustomTkinter> |
| darkdetect | used by CustomTkinter | BSD-3-Clause | <https://github.com/albertosottile/darkdetect> |
| Pillow | icons, images | MIT-CMU (HPND) | <https://github.com/python-pillow/Pillow> |
| pywin32 | Windows voices, shortcuts | PSF-2.0 | <https://github.com/mhammond/pywin32> |
| langdetect | language detection | Apache-2.0 | <https://github.com/Mimino666/langdetect> |
| aiohttp, yarl, multidict, frozenlist, aiosignal, propcache | network (edge-tts) | Apache-2.0 (aiohttp: Apache-2.0 AND MIT) | <https://github.com/aio-libs> |
| aiohappyeyeballs, typing-extensions | network, typing | PSF-2.0 | <https://pypi.org/project/aiohappyeyeballs/>, <https://pypi.org/project/typing-extensions/> |
| attrs, six, tabulate | helpers | MIT | <https://pypi.org/project/attrs/>, <https://pypi.org/project/six/>, <https://pypi.org/project/tabulate/> |
| idna | network | BSD-3-Clause | <https://github.com/kjd/idna> |
| packaging | helpers | Apache-2.0 OR BSD-2-Clause | <https://github.com/pypa/packaging> |
| certifi | HTTPS root certificates | MPL-2.0 ([notice](licenses/certifi-MPL-2.0-NOTICE.txt)) | <https://github.com/certifi/python-certifi> |
| PyInstaller bootloader | starts the portable EXE | GPL-2.0 with bootloader exception | <https://github.com/pyinstaller/pyinstaller> |

## Voices

- **Microsoft online voices** are a Microsoft service reached over the internet; no Microsoft voice
  data is included in FluentVoice. Not an official Microsoft API for other apps: see the README's
  Legal section.
- **Windows offline voices** come with Windows and are licensed with Windows for use on that PC.
- **Piper and Kokoro voices** are not bundled. You download them yourself in Settings → Voice
  Providers. Each voice keeps the licence of its recordings: see
  [`docs/VOICE_LICENSES.md`](docs/VOICE_LICENSES.md).

Microsoft, Windows and Microsoft Edge are trademarks of Microsoft Corporation. FluentVoice Pro is
independent and not affiliated with, sponsored or endorsed by Microsoft, the Open Home Foundation
(Piper), k2-fsa (sherpa-onnx) or the Kokoro authors.
