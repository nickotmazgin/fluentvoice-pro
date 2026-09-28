"""Write build/version_info.txt for PyInstaller (--version-file).

Windows shows FileDescription as the app name for the portable EXE (toasts, Task Manager,
"Open with"), so it reads "FluentVoice Pro" instead of a bare file name.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ver = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "fluentvoice" / "__init__.py").read_text()).group(1)
nums = tuple(int(x) for x in re.findall(r"\d+", ver)[:3]) + (0,)

out = ROOT / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Nick Otmazgin'),
      StringStruct('FileDescription', 'FluentVoice Pro'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'FluentVoicePro'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Nick Otmazgin. MIT License.'),
      StringStruct('OriginalFilename', 'FluentVoicePro.exe'),
      StringStruct('ProductName', 'FluentVoice Pro'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print(out)
