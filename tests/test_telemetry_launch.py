import pytest
from locdex.telemetry.events import build_routing_event
from locdex.routing.router import RoutingDecision
from locdex.routing.task_profile import TaskProfile
from locdex.runtime.hardware import HardwareProfile
from locdex.telemetry.queue import clear, enqueue, peek
from locdex.telemetry.sanitizer import sanitize_event
from locdex.telemetry.settings import mode, notice_once, set_mode


def sample():
    t = TaskProfile("bug_fix", "python", "medium", "multi_file", 4, 7, True, True, 6200, .71, .8, False, False)
    d = RoutingDecision("qwen", "local", .91, .91, 0, None, "balanced", "claude", {"qwen": .91, "claude": .96})
    h = HardwareProfile("Linux", "x86_64", 8, 32, 25, "cpu")
    return build_routing_event(task=t, decision=d, hardware=h, tests_passed=True).to_dict()


def test_default_basic_and_disabling_clears_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LOCDEX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("LOCDEX_TELEMETRY_MODE", raising=False)
    clear()
    assert mode() == "basic"
    enqueue(sample())
    assert peek()
    set_mode("off")
    assert mode() == "off"
    assert not peek()


def test_rejects_freeform_categories_and_path_identifiers():
    row = sample()
    row["task_class"] = "secret user project"
    with pytest.raises(ValueError):
        sanitize_event(row)
    row = sample()
    row["model_id"] = "C:/Users/Somebody"
    with pytest.raises(ValueError):
        sanitize_event(row)


def test_notice_once_and_opt_out(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOCDEX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("LOCDEX_TELEMETRY_MODE", raising=False)
    assert notice_once()
    message = capsys.readouterr().out
    assert "on by default" in message
    assert "telemetry disable" in message
    assert not notice_once()
    assert not capsys.readouterr().out
