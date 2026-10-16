"""Removing a Locdex model must reclaim its managed GGUF files, not only metadata."""
from __future__ import annotations

import json

import pytest

from locdex.models import manager


@pytest.fixture
def local_cache(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(root))
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("LOCDEX_MODEL_PATH", raising=False)
    monkeypatch.delenv("LOCDEX_MODEL", raising=False)
    return root


def _fixture(root, revision="rev1", *, manifest=True):
    folder = root / "models" / "smoke" / revision
    folder.mkdir(parents=True)
    model = folder / "smoke.gguf"
    model.write_bytes(b"GGUF")
    record = root / "manifests" / "smoke.json"
    if manifest:
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({"path": str(model)}), encoding="utf-8")
    return model, record


def test_remove_deletes_all_revisions_and_download_metadata(local_cache):
    root = local_cache
    first, record = _fixture(root)
    second, _ = _fixture(root, "rev2")
    metadata = root / "models" / "smoke" / "rev2" / ".cache" / "huggingface" / "downloads"
    metadata.mkdir(parents=True)
    (metadata / "metadata.json").write_text("{}", encoding="utf-8")
    other = root / "models" / "qwen25-7b" / "release" / "model.gguf"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"OTHER MODEL")

    assert manager.remove_model("smoke") is True
    assert not first.exists()
    assert not second.exists()
    assert not metadata.exists()
    assert not record.exists()
    assert not (root / "models" / "smoke").exists()
    assert other.is_file()
    assert manager.model_status("smoke")["installed"] is False
    assert manager.remove_model("smoke") is False


def test_remove_orphaned_cache_when_manifest_is_missing(local_cache):
    root = local_cache
    model, record = _fixture(root, manifest=False)
    assert not record.exists()
    assert manager.remove_model("smoke") is True
    assert not model.exists()


def test_remove_manifest_when_model_file_is_already_gone(local_cache):
    root = local_cache
    model, manifest = _fixture(root)
    model.unlink()
    assert manager.remove_model("smoke") is True
    assert not manifest.exists()
    assert not (root / "models" / "smoke").exists()


def test_locked_model_file_reports_error_and_preserves_record(local_cache, monkeypatch):
    root = local_cache
    model, manifest = _fixture(root)

    def locked(_):
        raise PermissionError("The process cannot access the file")

    monkeypatch.setattr(manager.shutil, "rmtree", locked)
    with pytest.raises(manager.ModelInstallError, match="Close any Locdex processes"):
        manager.remove_model("smoke")
    assert model.is_file()
    assert manifest.exists()


def test_remove_never_deletes_external_manifest_file(local_cache, tmp_path):
    external = tmp_path / "other-application" / "smoke.gguf"
    external.parent.mkdir()
    external.write_bytes(b"EXTERNAL")
    manifest = local_cache / "manifests" / "smoke.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"path": str(external)}), encoding="utf-8")

    with pytest.raises(manager.ModelInstallError, match="outside Locdex"):
        manager.remove_model("smoke")
    assert external.is_file()
    assert manifest.exists()


def test_remove_does_not_delete_env_overridden_model(local_cache, monkeypatch, tmp_path):
    managed, _ = _fixture(local_cache)
    monkeypatch.setenv("LOCDEX_MODEL", "smoke")
    external = tmp_path / "custom.gguf"
    external.write_bytes(b"EXTERNAL")
    monkeypatch.setenv("LOCDEX_MODEL_PATH", str(external))

    with pytest.raises(manager.ModelInstallError, match="LOCDEX_MODEL_PATH"):
        manager.remove_model("smoke")
    assert external.is_file()
    assert managed.is_file()
