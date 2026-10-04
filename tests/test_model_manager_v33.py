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
    assert {row["model"] for row in rows} == {
        "smoke",
        "qwen25-3b",
        "qwen25-7b",
        "kimi",
        "qwen25-14b",
        "deepseek-lite",
        "qwen3-coder",
        "qwen",
    }


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


def test_model_catalog_spans_hardware_tiers(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path / "cache"))
    rows = manager.all_model_statuses()
    by_key = {row["model"]: row for row in rows}

    assert by_key["smoke"]["profile_status"] == "development"
    assert by_key["qwen25-3b"]["recommended_ram_gb"] == 8
    assert by_key["qwen25-7b"]["recommended_ram_gb"] == 12
    assert by_key["qwen25-14b"]["recommended_ram_gb"] == 16
    assert by_key["qwen3-coder"]["recommended_ram_gb"] == 32
    assert by_key["qwen"]["profile_status"] == "supported"
    assert by_key["qwen25-7b"]["family"] == "qwen2.5-coder"
