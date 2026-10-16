"""Offline tests for the Docker-only LocdexBench execution boundary."""
from __future__ import annotations

from pathlib import Path

import pytest

from locdex.benchmark.controls import validate_agent_changes
from locdex.benchmark.isolated_runner import (
    BenchmarkRunError, docker_arguments, validate_image, validate_trial_record,
)
from locdex.benchmark.manifest import load_manifest


IMAGE = "sha256:" + "a" * 64
ROOT = Path(__file__).resolve().parents[1]


def _call(tmp_path: Path, *, grader: bool = False) -> list[str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    if grader:
        path = tmp_path / "outside-agent-grader.py"
        path.write_text("assert True", encoding="utf-8")
        return docker_arguments(
            image=IMAGE, container_name="grader-test", workspace=workspace,
            command=["python", "-m", "unittest"], readonly_workspace=True,
            hidden_grader=path,
        )
    model = tmp_path / "model.gguf"
    model.write_bytes(b"fixture-model")
    return docker_arguments(
        image=IMAGE, container_name="agent-test", workspace=workspace,
        command=["locdex", "task"], model_path=model, model_key="smoke",
    )


def test_agent_container_has_no_network_or_grader(tmp_path):
    args = _call(tmp_path)
    assert args[:3] == ["docker", "run", "--rm"]
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges" in args
    assert "--read-only" in args
    assert "LOCDEX_CLOUD_ENABLED=0" in args
    assert "LOCDEX_TELEMETRY_MODE=off" in args
    assert "LOCDEX_MODEL=smoke" in args
    assert args[args.index("--memory") + 1] == "8g"
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
    assert len(mounts) == 2
    assert all("/grader" not in m for m in mounts)
    assert any("target=/models/model.gguf,readonly=true" in m for m in mounts)
    assert any("target=/workspace,readonly=false" in m for m in mounts)
    args12 = docker_arguments(image=IMAGE, container_name="agent-12g", workspace=tmp_path,
        command=["locdex", "task"], memory_gb=12)
    assert args12[args12.index("--memory") + 1] == "12g"
    with pytest.raises(BenchmarkRunError, match="memory_gb"):
        docker_arguments(image=IMAGE, container_name="unsafe", workspace=tmp_path,
            command=["true"], memory_gb=128)


def test_grader_only_mounts_in_separate_readonly_container(tmp_path):
    args = _call(tmp_path, grader=True)
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
    assert any("target=/workspace,readonly=true" in m for m in mounts)
    assert any("target=/tmp/test_hidden.py,readonly=true" in m for m in mounts)
    assert all("/models/" not in m for m in mounts)


def test_no_unpinned_or_dangerous_images(tmp_path):
    for value in ["python:latest", "repo:stable", "latest", "sha256:abc", "evil\nimage"]:
        with pytest.raises(BenchmarkRunError):
            validate_image(value)
    validate_image(IMAGE)
    validate_image("registry.example/locdexbench@sha256:" + "f" * 64)
    with pytest.raises(BenchmarkRunError, match="grader"):
        docker_arguments(
            image=IMAGE, container_name="invalid", workspace=tmp_path,
            command=["echo", "unsafe"], hidden_grader=tmp_path / "hidden.py",
            readonly_workspace=False,
        )


def test_mount_sources_cannot_inject_docker_options(tmp_path):
    with pytest.raises(BenchmarkRunError, match="Commas"):
        docker_arguments(
            image=IMAGE, container_name="unsafe", workspace=tmp_path / "a,readonly=true",
            command=["echo", "test"],
        )


def test_trial_record_strict_allowlist():
    record = {
        "schema": "locdexbench-local-v0",
        "task_id": "py-arithmetic-edge-001",
        "base_commit": "c" * 40,
        "model": "smoke", "mode": "local-only",
        "model_sha256": "d" * 64,
        "container_image": IMAGE,
        "status": "grader_failed", "verified": False,
        "visible_passed": True, "hidden_passed": False,
        "wall_seconds": 12.5, "max_steps": 12, "memory_gb": 8,
    }
    validate_trial_record(record)
    with pytest.raises(ValueError):
        validate_trial_record({**record, "private_path": "C:/Users/private"})
    with pytest.raises(ValueError):
        validate_trial_record({**record, "status": "passed", "verified": False})
    with pytest.raises(ValueError):
        validate_trial_record({**record, "memory_gb": 64})


def test_protected_file_checks_ignore_git_metadata_but_not_tests(tmp_path):
    task = load_manifest(ROOT / "benchmarks/tasks/py-arithmetic-edge-001.yaml")
    original, result = tmp_path / "original", tmp_path / "result"
    original.mkdir()
    result.mkdir()
    for folder in (original, result):
        (folder / ".git").mkdir()
        (folder / ".git/index").write_text("metadata", encoding="utf-8")
        (folder / "core.py").write_text("baseline", encoding="utf-8")
    (result / ".git/index").write_text("modified-index", encoding="utf-8")
    (result / "core.py").write_text("correct", encoding="utf-8")
    validate_agent_changes(task, original, result)
    (result / "test_hidden.py").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="protected"):
        validate_agent_changes(task, original, result)


def test_benchmark_cli_has_isolated_local_option():
    from locdex.cli.app import build_parser

    options = build_parser().parse_args([
        "benchmark", "run-local", "--manifest", "benchmarks/tasks/example.yaml",
        "--image", IMAGE, "--model", "smoke", "--model-path", "model.gguf",
        "--memory-gb", "12",
    ])
    assert options.benchmark_action == "run-local"
    assert options.model == "smoke"
    assert options.memory_gb == 12
