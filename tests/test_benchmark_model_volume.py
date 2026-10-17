"""Verify persistent GGUF caches do not compromise LocdexBench model isolation."""
from __future__ import annotations

import subprocess

import pytest

from locdex.benchmark import isolated_runner


IMAGE = "sha256:" + "a" * 64
DIGEST = "b" * 64


def test_model_volume_is_readonly_and_not_a_windows_bind(tmp_path):
    args = isolated_runner.docker_arguments(
        image=IMAGE,
        container_name="agent",
        workspace=tmp_path,
        command=["locdex", "task"],
        model_key="qwen25-3b",
        model_volume="locdex-qwen25-3b-native",
    )
    assert "type=volume,source=locdex-qwen25-3b-native,target=/models,readonly" in args
    assert not any("source=/models/model.gguf" in item for item in args)
    assert "LOCDEX_MODEL_PATH=/models/model.gguf" in args
    assert "--network" in args and "none" in args


def test_model_volume_never_reaches_grader(tmp_path):
    with pytest.raises(isolated_runner.BenchmarkRunError, match="grading"):
        isolated_runner.docker_arguments(
            image=IMAGE,
            container_name="grader",
            workspace=tmp_path,
            command=["python", "-m", "unittest"],
            model_volume="locdex-qwen25-3b-native",
            readonly_workspace=True,
        )


def test_path_and_volume_are_exclusive(tmp_path):
    with pytest.raises(isolated_runner.BenchmarkRunError, match="mutually exclusive"):
        isolated_runner.docker_arguments(
            image=IMAGE,
            container_name="agent",
            workspace=tmp_path,
            command=["true"],
            model_path=tmp_path / "test.gguf",
            model_volume="locdex-qwen25-3b-native",
        )


def test_reuse_existing_cache_checks_digest_without_copy(monkeypatch, tmp_path):
    subprocess_calls = []
    agent_calls = []

    def fake_run(args, **kwargs):
        subprocess_calls.append(args)
        assert args[:3] == ["docker", "volume", "inspect"]
        return subprocess.CompletedProcess(args, 0, stdout="[]")

    def fake_docker(args, name, timeout):
        agent_calls.append((args, name, timeout))
        return subprocess.CompletedProcess(args, 0, stdout=DIGEST + "\n")

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(isolated_runner, "_call_docker", fake_docker)
    volume, mode = isolated_runner._prepare_model_volume(
        image=IMAGE, model_path=tmp_path / "model.gguf", digest=DIGEST,
        requested_volume="locdex-qwen25-3b-native",
    )
    assert (volume, mode) == ("locdex-qwen25-3b-native", "reused")
    assert len(agent_calls) == 1
    assert "type=volume,source=locdex-qwen25-3b-native,target=/models,readonly" in agent_calls[0][0]


def test_missing_supplied_volume_never_created(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, stdout="")

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    with pytest.raises(isolated_runner.BenchmarkRunError, match="does not exist"):
        isolated_runner._prepare_model_volume(
            image=IMAGE, model_path=tmp_path / "model.gguf", digest=DIGEST,
            requested_volume="user-provided-volume",
        )
    assert len(calls) == 1


def test_mismatched_supplied_volume_rejected_without_delete(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="[]")

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        isolated_runner, "_call_docker",
        lambda args, name, timeout: subprocess.CompletedProcess(args, 0, stdout="0" * 64),
    )
    with pytest.raises(isolated_runner.BenchmarkRunError, match="checksum mismatch"):
        isolated_runner._prepare_model_volume(
            image=IMAGE, model_path=tmp_path / "model.gguf", digest=DIGEST,
            requested_volume="user-provided-volume",
        )
    assert len(calls) == 1  # inspect only, never remove or overwrite


def test_cache_miss_stages_once_then_verifies(monkeypatch, tmp_path):
    calls = []
    docker_calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:3] == ["docker", "volume", "inspect"]:
            return subprocess.CompletedProcess(args, 1)
        return subprocess.CompletedProcess(args, 0)

    def fake_docker(args, name, timeout):
        docker_calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=DIGEST + "\n" if "model-verify-" in name else "",
        )

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(isolated_runner, "_call_docker", fake_docker)
    volume, mode = isolated_runner._prepare_model_volume(
        image=IMAGE, model_path=tmp_path / "model.gguf", digest=DIGEST,
    )
    assert (volume, mode) == ("locdexbench-gguf-" + DIGEST[:24], "staged")
    assert ["docker", "volume", "create", volume] in calls
    assert len(docker_calls) == 2
    assert "type=volume,source=" + volume + ",target=/stage" in docker_calls[0]
    assert "type=volume,source=" + volume + ",target=/models,readonly" in docker_calls[1]
