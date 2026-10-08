import importlib.util
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _make_zip():
    spec = importlib.util.spec_from_file_location("make_zip", ROOT / "scripts" / "make_zip.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.make_zip


def test_release_zip_uses_forward_slashes(tmp_path):
    src = tmp_path / "FluentVoicePro"
    (src / "_internal" / "sub").mkdir(parents=True)
    (src / "FluentVoicePro.exe").write_bytes(b"exe")
    (src / "_internal" / "sub" / "data.txt").write_text("hi")
    out = tmp_path / "out.zip"

    assert _make_zip()(src, out) == 2
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == ["FluentVoicePro.exe", "_internal/sub/data.txt"]
        assert z.read("_internal/sub/data.txt") == b"hi"
        assert z.testzip() is None


def test_release_script_does_not_use_compress_archive():
    script = (ROOT / "scripts" / "create-release-zips.ps1").read_text(encoding="utf-8")
    assert "Compress-Archive" not in script
    assert script.count('python (Join-Path $Root "scripts\\make_zip.py")') == 2
