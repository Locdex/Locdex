"""Focused regression tests for private benchmark progress reporting."""
from __future__ import annotations

import subprocess

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
    clock = iter([0, 0, 11, 11])
    monkeypatch.setattr(isolated_runner.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(isolated_runner.subprocess, "Popen", lambda *a, **kw: DummyProcess(hangs=True))
    monkeypatch.setattr(isolated_runner.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    code, diag = isolated_runner._run_agent_with_progress(["docker", "run"], "agent-test", 10)
    assert code == 124
    assert diag["timed_out"] is True
    assert diag["stage"] == "agent_execution"
    assert "timed out" in capsys.readouterr().out
