from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

from ..agent import AgentEngine
from ..models import get_model_profile, model_status
from ..runtime import detect_hardware, run_prompt, runtime_status


QUALIFICATION_PROMPT = "Reply with exactly: LOCDEX_QUALIFY_OK"
QUALIFICATION_EXPECTED = "LOCDEX_QUALIFY_OK"


def _reports_dir() -> Path:
    root = Path(user_cache_dir("locdex", "Locdex")).expanduser().resolve()
    return root / "qualifications"


def _save_report(report: dict[str, Any]) -> str:
    directory = _reports_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{report['model']}-{stamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def _init_fixture(repo: Path) -> None:
    (repo / "calculator.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    (repo / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    try:
        subprocess.run(
            ["git", "init"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        # Git metadata improves diagnostics but is not required for the bounded
        # qualification task itself.
        pass


def _hardware_eligibility(profile, hardware, force: bool) -> tuple[bool, str]:
    total = hardware.total_ram_gb
    if total is None:
        return True, "RAM could not be measured; proceeding with runtime checks."
    if total >= profile.minimum_ram_gb:
        return True, (
            f"Detected {total:.2f} GiB RAM; model minimum is "
            f"{profile.minimum_ram_gb} GiB."
        )
    if force:
        return True, (
            f"Forced qualification below profile minimum: {total:.2f} GiB "
            f"detected vs {profile.minimum_ram_gb} GiB minimum."
        )
    return False, (
        f"Qualification skipped: {total:.2f} GiB RAM detected but "
        f"{profile.minimum_ram_gb} GiB is the model minimum. "
        "Use --force-hardware only if you intentionally want to test anyway."
    )


def qualify_model(
    key: str,
    *,
    max_steps: int = 8,
    force_hardware: bool = False,
    agent_task: bool = True,
    save_report: bool = True,
) -> dict[str, Any]:
    profile = get_model_profile(key)
    status = model_status(profile.key)
    hardware = detect_hardware()
    runtime = runtime_status(hardware)

    eligible, eligibility_reason = _hardware_eligibility(
        profile,
        hardware,
        force_hardware,
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "model": profile.key,
        "display_name": profile.display_name,
        "profile_status": profile.status,
        "hardware_tier": profile.hardware_tier,
        "model_installed": bool(status["installed"]),
        "hardware": hardware.to_dict(),
        "runtime": runtime.to_dict(),
        "hardware_eligible": eligible,
        "hardware_reason": eligibility_reason,
        "prompt_probe": None,
        "agent_probe": None,
        "passed": False,
        "status": "pending",
        "report_path": None,
    }

    if not eligible:
        report["status"] = "skipped_hardware"
        if save_report:
            report["report_path"] = _save_report(report)
        return report

    if not status["installed"]:
        report["status"] = "model_not_installed"
        report["error"] = (
            f"Model {profile.key!r} is not installed. "
            f"Run: locdex model install {profile.key}"
        )
        if save_report:
            report["report_path"] = _save_report(report)
        return report

    if not runtime.healthy:
        report["status"] = "runtime_unhealthy"
        report["error"] = runtime.reason
        if save_report:
            report["report_path"] = _save_report(report)
        return report

    prompt_started = time.perf_counter()
    try:
        prompt_result = run_prompt(
            QUALIFICATION_PROMPT,
            model_key=profile.key,
            max_tokens=32,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        report["prompt_probe"] = {
            "passed": False,
            "elapsed_seconds": round(time.perf_counter() - prompt_started, 3),
            "error": str(exc)[:1000],
        }
        report["status"] = "prompt_failed"
        if save_report:
            report["report_path"] = _save_report(report)
        return report

    prompt_text = str(prompt_result.get("text", "")).strip()
    prompt_passed = prompt_text == QUALIFICATION_EXPECTED
    report["prompt_probe"] = {
        "passed": prompt_passed,
        "elapsed_seconds": round(time.perf_counter() - prompt_started, 3),
        "backend": prompt_result.get("backend"),
        "text": prompt_text[:200],
        "usage": prompt_result.get("usage"),
    }
    if not prompt_passed:
        report["status"] = "prompt_mismatch"
        if save_report:
            report["report_path"] = _save_report(report)
        return report

    if not agent_task:
        report["passed"] = True
        report["status"] = "passed_prompt_only"
        if save_report:
            report["report_path"] = _save_report(report)
        return report

    with tempfile.TemporaryDirectory(prefix="locdex-qualify-") as td:
        repo = Path(td)
        _init_fixture(repo)
        original_test = (repo / "test_calculator.py").read_text(encoding="utf-8")

        agent_started = time.perf_counter()
        try:
            result = AgentEngine(model_key=profile.key).execute(
                "Fix calculator.py so the existing tests pass. Do not change tests.",
                str(repo),
                max_steps=max(1, min(int(max_steps), 20)),
                routing_mode="local_only",
                write_scope=["calculator.py"],
                progress=None,
            )
        except Exception as exc:  # noqa: BLE001
            report["agent_probe"] = {
                "passed": False,
                "elapsed_seconds": round(time.perf_counter() - agent_started, 3),
                "error": str(exc)[:1000],
            }
            report["status"] = "agent_failed"
            if save_report:
                report["report_path"] = _save_report(report)
            return report

        verification = result.get("verification") or {}
        tests_unchanged = (
            (repo / "test_calculator.py").read_text(encoding="utf-8")
            == original_test
        )
        agent_passed = (
            result.get("status") == "completed"
            and verification.get("passed") is True
            and tests_unchanged
            and not result.get("rollback_performed")
        )
        report["agent_probe"] = {
            "passed": agent_passed,
            "elapsed_seconds": round(time.perf_counter() - agent_started, 3),
            "status": result.get("status"),
            "steps": result.get("steps"),
            "files_modified": result.get("files_modified") or [],
            "attempted_files_modified": result.get("attempted_files_modified") or [],
            "verification": verification,
            "rollback_performed": bool(result.get("rollback_performed")),
            "tests_unchanged": tests_unchanged,
        }

    report["passed"] = bool(report["prompt_probe"]["passed"] and report["agent_probe"]["passed"])
    report["status"] = "passed" if report["passed"] else "agent_probe_failed"
    if save_report:
        report["report_path"] = _save_report(report)
    return report
