"""Start-with-Windows / shortcut management — source install and portable EXE."""
import json
import sys
from pathlib import Path

import pytest

from fluentvoice import shortcuts


class FakeShortcut:
    """Stands in for a WScript.Shell shortcut; Save() writes JSON so tests can read it back."""

    def __init__(self, path):
        self.path = Path(path)
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.TargetPath = data.get("TargetPath", "")
        self.Arguments = data.get("Arguments", "")
        self.WorkingDirectory = data.get("WorkingDirectory", "")
        self.IconLocation = data.get("IconLocation", "")
        self.Description = data.get("Description", "")

    def Save(self):
        self.path.write_text(json.dumps({k: getattr(self, k) for k in (
            "TargetPath", "Arguments", "WorkingDirectory", "IconLocation", "Description")}))


class FakeShell:
    def __init__(self, root: Path):
        self.root = root

    def SpecialFolders(self, name):
        p = self.root / name
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    def CreateShortcut(self, path):
        return FakeShortcut(path)


def read(p: Path) -> dict:
    return json.loads(p.read_text())


@pytest.fixture
def shell(tmp_path, monkeypatch):
    fake = FakeShell(tmp_path)
    monkeypatch.setattr(shortcuts, "_shell", lambda: fake)
    monkeypatch.setattr(shortcuts, "_notify_shell", lambda: None)
    return fake


@pytest.fixture
def portable(tmp_path, monkeypatch):
    exe = tmp_path / "Portable" / "FluentVoicePro.exe"
    exe.parent.mkdir()
    exe.write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    return exe


def test_launch_command_source_uses_python_module():
    target, args = shortcuts.launch_command()
    assert Path(target).name.lower() in ("pythonw.exe", "python.exe", Path(sys.executable).name.lower())
    assert args == "-m fluentvoice.tray"
    assert shortcuts.launch_command("--gui")[1] == "-m fluentvoice.cli --gui"


def test_launch_command_portable_runs_exe_directly(portable):
    assert shortcuts.launch_command() == (str(portable.resolve()), "")
    assert shortcuts.launch_command("--gui") == (str(portable.resolve()), "--gui")
    assert shortcuts.app_dir() == portable.resolve().parent


def test_startup_toggle(shell, portable):
    assert not shortcuts.startup_enabled()
    assert shortcuts.set_startup(True) is True
    lnk = read(shortcuts.startup_path())
    assert lnk["TargetPath"] == str(portable.resolve())
    assert lnk["Arguments"] == ""  # no args = tray daemon
    assert lnk["WorkingDirectory"] == str(portable.resolve().parent)
    assert shortcuts.set_startup(False) is False
    assert not shortcuts.startup_path().exists()
    shortcuts.set_startup(False)  # removing twice is fine


def test_create_and_remove_shortcuts(shell, portable):
    made = shortcuts.create_shortcuts()
    assert len(made) == 1 + len(shortcuts.START_MENU_ITEMS)
    assert shortcuts.shortcuts_installed()
    assert read(shortcuts.desktop_path())["Arguments"] == "--gui"
    stop = read(shortcuts.start_menu_dir() / "FluentVoice Emergency Stop.lnk")
    assert stop["Arguments"] == "--stop"
    shortcuts.remove_shortcuts()
    assert not shortcuts.shortcuts_installed()
    assert not shortcuts.start_menu_dir().exists()


def test_repair_repoints_moved_portable(shell, portable, tmp_path):
    shortcuts.set_startup(True)
    shortcuts.create_shortcuts()
    # Simulate the user moving the portable folder: old links point at the previous exe.
    old_exe = str(tmp_path / "OldPlace" / "FluentVoicePro.exe")
    for p in (shortcuts.startup_path(), shortcuts.desktop_path()):
        d = read(p)
        d["TargetPath"] = old_exe
        p.write_text(json.dumps(d))
    assert shortcuts.repair_moved_portable() == 2
    assert read(shortcuts.startup_path())["TargetPath"] == str(portable.resolve())
    assert read(shortcuts.desktop_path())["Arguments"] == "--gui"
    assert shortcuts.repair_moved_portable() == 0  # already correct


def test_repair_leaves_source_install_links_alone(shell, portable):
    p = shortcuts.startup_path()
    p.write_text(json.dumps({"TargetPath": r"C:\Python314\pythonw.exe", "Arguments": "-m fluentvoice.tray"}))
    assert shortcuts.repair_moved_portable() == 0
    assert read(p)["TargetPath"] == r"C:\Python314\pythonw.exe"


def test_repair_is_noop_for_source_install(shell):
    assert shortcuts.repair_moved_portable() == 0
