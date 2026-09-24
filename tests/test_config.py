"""Config persistence tests."""
from fluentvoice import config


def test_atomic_save_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    cfg = config.load_config()
    assert cfg["check_updates"] is True and cfg["skipped_update_version"] == ""
    cfg["voice"] = "he-IL-HilaNeural"
    cfg["preferred_voices"]["hebrew"] = "he-IL-HilaNeural"
    config.save_config(cfg)
    again = config.load_config()
    assert again["voice"] == "he-IL-HilaNeural"
    assert again["preferred_voices"]["hebrew"] == "he-IL-HilaNeural"
    # no temp files left behind
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


def test_corrupt_config_falls_back_to_defaults(monkeypatch, tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", p)
    assert config.load_config()["voice"] == config.DEFAULT_CONFIG["voice"]
