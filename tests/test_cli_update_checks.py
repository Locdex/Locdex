"""Release checks should be private, offline-aware, bounded and nonblocking."""
from __future__ import annotations

import json
import threading
import time

import requests

from locdex.cli import updates
from locdex.cli.app import cli


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "_cache_path", lambda: tmp_path / "cache.json")
    monkeypatch.setattr(updates, "_settings_path", lambda: tmp_path / "settings.json")
    for name in ("LOCDEX_OFFLINE", "LOCDEX_NO_UPDATE_CHECK", "CI"):
        monkeypatch.delenv(name, raising=False)


def test_latest_stable_excludes_prereleases_and_yanked(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    observed = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "releases": {
                    "1.4.0": [{"yanked": False}],
                    "1.4.2": [{"yanked": False}],
                    "1.5.0rc1": [{"yanked": False}],
                    "1.9.0": [{"yanked": True}],
                    "invalid": [{"yanked": False}],
                    "2.0.0": [],
                }
            }

    def fake_get(url, **kwargs):
        observed.append((url, kwargs))
        return Response()

    monkeypatch.setattr(updates.requests, "get", fake_get)
    assert updates.latest_stable_version() == "1.4.2"
    assert observed[0][0] == updates.PYPI_URL
    assert observed[0][1]["timeout"] == updates.REQUEST_TIMEOUT_SECONDS
    assert "user-agent" not in str(observed[0][1]["headers"]).lower() or "Locdex" in str(observed[0][1]["headers"])
    assert not any(term in str(observed[0]) for term in ("C:\\Users\\", "/home/", "repo_path"))


def test_background_checker_does_not_block_and_notifies_once(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    started = threading.Event()
    allow_finish = threading.Event()

    def fake_latest():
        started.set()
        assert allow_finish.wait(2)
        return "9.5.0"

    monkeypatch.setattr(updates, "latest_stable_version", fake_latest)
    checker = updates.BackgroundUpdateCheck()
    t0 = time.monotonic()
    checker.start()
    assert time.monotonic() - t0 < 0.5
    assert started.wait(1)
    assert checker.poll_notice() is None
    allow_finish.set()
    assert checker._thread is not None
    checker._thread.join(timeout=2)
    notice = checker.poll_notice()
    assert "Locdex update available:" in notice
    assert "9.5.0" in notice
    assert "python -m pip install --upgrade locdex" in notice
    assert "npm install -g @locdex/cli@latest --foreground-scripts" in notice
    assert "will not install updates automatically" in notice
    assert "\\n" not in notice
    assert updates.RELEASES_URL in notice
    assert checker.poll_notice() is None


def test_recent_cache_skips_network_and_preserves_notice(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    updates._write_json(
        updates._cache_path(),
        {"latest": "9.5.0", "checked_at": time.time()},
    )

    def must_not_call():
        raise AssertionError("recent results must never recheck")

    monkeypatch.setattr(updates, "latest_stable_version", must_not_call)
    checker = updates.BackgroundUpdateCheck()
    checker.start()
    assert checker._thread is None
    assert "9.5.0" in checker.poll_notice()


def test_offline_and_automatic_off_do_not_access_network(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(
        updates, "latest_stable_version",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected network access")),
    )
    monkeypatch.setenv("LOCDEX_OFFLINE", "1")
    checker = updates.BackgroundUpdateCheck()
    checker.start()
    assert checker._thread is None
    assert checker.poll_notice() is None
    assert "error" in updates.check_now()
    monkeypatch.delenv("LOCDEX_OFFLINE")
    updates.set_automatic_checks(False)
    checker = updates.BackgroundUpdateCheck()
    checker.start()
    assert checker._thread is None
    assert checker.poll_notice() is None
    assert not updates.cached_status()["automatic"]
    updates.set_automatic_checks(True)
    assert updates.cached_status()["automatic"]


def test_sandbox_network_disabled_skips_check(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    checker = updates.BackgroundUpdateCheck()
    checker.start(network_allowed=False)
    assert checker._thread is None
    assert checker.poll_notice() is None
    assert updates.check_now(network_allowed=False)["error"].startswith("Update checks disabled")


def test_failed_network_does_not_interrupt_cli(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    def fake_latest():
        raise requests.exceptions.Timeout("server unavailable")

    monkeypatch.setattr(updates, "latest_stable_version", fake_latest)
    status = updates.check_now()
    assert status["current"] == updates.__version__
    assert status["update_available"] is False
    assert "unavailable" in status["error"]


def test_cli_update_controls_off_status_on_and_check(monkeypatch, tmp_path, capsys):
    _isolate(monkeypatch, tmp_path)
    assert cli(["update", "off"]) == 0
    assert cli(["update", "status"]) == 0
    assert '"automatic": false' in capsys.readouterr().out.lower()
    assert cli(["update", "on"]) == 0
    monkeypatch.setattr(updates, "latest_stable_version", lambda: "9.5.0")
    assert cli(["update", "check"]) == 0
    output = capsys.readouterr().out
    assert '"latest": "9.5.0"' in output
    assert '"update_available": true' in output
    assert cli(["update", "status"]) == 0


def test_no_update_notification_on_equal_or_older_releases(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    updates._write_json(updates._cache_path(), {
        "latest": updates.__version__, "checked_at": time.time()
    })
    assert updates.update_notice(updates.cached_status()) is None
    updates._write_json(updates._cache_path(), {"latest": "1.3.1"})
    assert updates.update_notice(updates.cached_status()) is None


def test_background_checker_keeps_no_package_install_capability():
    import inspect
    source = inspect.getsource(updates)
    assert "subprocess" not in source
    assert "pip install" not in source
    assert "npm install" not in source
    assert "requests.post" not in source


def test_interactive_launch_starts_update_check_without_waiting(
    monkeypatch, tmp_path, capsys,
):
    from types import SimpleNamespace
    from locdex.cli import interactive

    events = []

    class FakeCheck:
        def __init__(self):
            self.seen = False

        def start(self, *, network_allowed=True):
            events.append(("checking", network_allowed))

        def poll_notice(self):
            if not self.seen:
                self.seen = True
                return "Locdex 9.5.0 is available."
            return None

    class FakePool:
        def start(self, model):
            events.append(("preload", model))

    state = SimpleNamespace(
        model="smoke",
        sandbox_mode="workspace-network",
        repo_path=str(tmp_path),
        save=lambda: events.append("saved"),
    )
    monkeypatch.setattr(interactive, "_find_resume_session", lambda *a: state)
    monkeypatch.setattr(interactive, "_print_header", lambda *a: None)
    monkeypatch.setattr(interactive, "BackgroundUpdateCheck", FakeCheck)
    monkeypatch.setattr("builtins.input", lambda prompt: "exit")

    assert interactive._run_interactive_impl(str(tmp_path), model_pool=FakePool()) == 0
    assert events[0] == ("checking", True)
    assert events[1] == ("preload", "smoke")
    assert "Locdex 9.5.0 is available." in capsys.readouterr().out
