"""Focused regression tests for private benchmark progress reporting."""
from __future__ import annotations

import subprocess
import sys

from locdex.benchmark import isolated_runner


class DummyProcess:
    def __init__(self, returncode=0, hangs=False):
        self.returncode = None if hangs else returncode
        self.hangs = hangs

    def wait(self, timeout=None):
        if self.hangs:
            raise subprocess.TimeoutExpired("docker", timeout)
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_success_reports_execution_stage(monkeypatch, capsys):
    monkeypatch.setattr(isolated_runner.subprocess, "Popen", lambda *a, **kw: DummyProcess())
    monkeypatch.setattr(isolated_runner.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    code, diag = isolated_runner._run_agent_with_progress(["docker", "run"], "agent-test", 10)
    assert code == 0
    assert diag["stage"] == "agent_execution"
    assert diag["timed_out"] is False
    assert "Agent starting" in capsys.readouterr().out


def test_timeout_reports_stage_without_raw_output(monkeypatch, capsys):
    clock = iter([0, 0, 11, 11, 11])
    monkeypatch.setattr(isolated_runner.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(isolated_runner.subprocess, "Popen", lambda *a, **kw: DummyProcess(hangs=True))
    monkeypatch.setattr(isolated_runner.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    code, diag = isolated_runner._run_agent_with_progress(["docker", "run"], "agent-test", 10)
    assert code == 124
    assert diag["timed_out"] is True
    assert diag["stage"] == "agent_execution"
    assert "timed out" in capsys.readouterr().out


def test_agent_container_receives_explicit_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "300")
    args = isolated_runner.docker_arguments(
        image="sha256:" + "a" * 64,
        container_name="agent-test",
        workspace=tmp_path,
        command=["locdex", "task"],
        model_key="qwen25-3b",
    )
    assert "LOCDEX_INFERENCE_TIMEOUT_SECONDS=300" in args
    assert "LOCDEX_BENCH_PROGRESS=1" in args


def test_grader_does_not_inherit_model_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "300")
    args = isolated_runner.docker_arguments(
        image="sha256:" + "a" * 64,
        container_name="grade-test",
        workspace=tmp_path,
        command=["python", "-m", "unittest"],
        readonly_workspace=True,
    )
    assert not any("LOCDEX_INFERENCE_TIMEOUT_SECONDS=" in arg for arg in args)
    assert "LOCDEX_BENCH_PROGRESS=1" not in args


def test_real_subprocess_phase_event_is_forwarded(monkeypatch, capsys):
    """Read actual stderr produced by a process, not only mocked Popen."""
    monkeypatch.setattr(
        isolated_runner.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0),
    )
    code, diag = isolated_runner._run_agent_with_progress(
        [sys.executable, "-c",
         "import sys; print('[Agent] Preparing repository context and selecting local execution plan...', file=sys.stderr, flush=True)"],
        "agent-test",
        5,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert diag["progress_events"] == 1
    assert diag["phase"] == "context_preparation"
    assert "Preparing repository context" in out


def test_non_progress_stderr_is_not_exposed(monkeypatch, capsys):
    monkeypatch.setattr(
        isolated_runner.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0),
    )
    code, diag = isolated_runner._run_agent_with_progress(
        [sys.executable, "-c",
         "import sys; print('DO_NOT_PRINT_PRIVATE_MODEL_OUTPUT', file=sys.stderr, flush=True)"],
        "agent-test",
        5,
    )
    assert code == 0
    assert diag["progress_events"] == 0
    assert diag["phase"] == "unobserved"
    assert diag["stderr_bytes"] > 0
    assert "DO_NOT_PRINT_PRIVATE_MODEL_OUTPUT" not in capsys.readouterr().out
