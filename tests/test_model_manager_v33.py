from __future__ import annotations

import json

from locdex.models import manager


def test_selected_model_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("LOCDEX_MODEL", raising=False)
    assert manager.select_model("smoke") == "smoke"
    assert manager.selected_model_key() == "smoke"


def test_all_statuses_include_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path / "cache"))
    rows = manager.all_model_statuses()
    assert {row["model"] for row in rows} == {"smoke", "qwen", "kimi"}


def test_remove_managed_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "cache"
    model_path = root / "models" / "smoke" / "abc123" / "smoke.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"gguf")
    manifest = root / "manifests" / "smoke.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"path": str(model_path)}), encoding="utf-8")
    assert manager.remove_model("smoke") is True
    assert not model_path.exists()
    assert not manifest.exists()
