import json
from pathlib import Path

from locdex import model_manager
from locdex.config import LocalModelConfig


def _config(tmp_path: Path, **overrides):
    values = {
        "model_key": "qwen",
        "repo_id": "example/repo",
        "filename_pattern": "*Q4_K_M.gguf",
        "revision": None,
        "expected_sha256": None,
        "explicit_model_path": None,
        "cache_dir": tmp_path,
        "auto_download": True,
        "n_ctx": 4096,
        "n_threads": 2,
        "n_gpu_layers": 0,
        "max_tokens": 1024,
        "temperature": 0.1,
        "max_agent_steps": 4,
    }
    values.update(overrides)
    return LocalModelConfig(**values)


def test_explicit_model_path_is_respected(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf-test")
    cfg = _config(tmp_path, explicit_model_path=model)
    assert model_manager.installed_model_path(cfg) == model.resolve()


def test_manifest_model_is_detected(tmp_path):
    model = tmp_path / "models" / "repo" / "abc" / "model.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"gguf-test")
    (tmp_path / "manifests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifests" / "qwen.json").write_text(
        json.dumps({"path": str(model), "repo_id": "example/repo"}), encoding="utf-8"
    )
    assert model_manager.installed_model_path(_config(tmp_path)) == model
