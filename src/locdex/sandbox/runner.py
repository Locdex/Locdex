from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .policy import SandboxMode, profile_for_mode


@dataclass(frozen=True)
class SandboxCapabilities:
    platform: str
    backend: str
    os_isolation: bool
    network_isolation: bool
    filesystem_isolation: bool
    reason: str
    process_isolation: bool = False
    helper_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "backend": self.backend,
            "os_isolation": self.os_isolation,
            "process_isolation": self.process_isolation,
            "network_isolation": self.network_isolation,
            "filesystem_isolation": self.filesystem_isolation,
            "helper_path": self.helper_path,
            "reason": self.reason,
        }


def _windows_helper_candidates() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("LOCDEX_WINDOWS_SANDBOX", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    discovered = shutil.which("locdex-windows-sandbox")
    if discovered:
        candidates.append(Path(discovered))

    candidates.append(
        Path(__file__).resolve().parent / "bin" / "locdex-windows-sandbox.exe"
    )

    root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            root / "native" / "windows-sandbox" / "target" / "release"
            / "locdex-windows-sandbox.exe",
            root / "native" / "windows-sandbox" / "target" / "debug"
            / "locdex-windows-sandbox.exe",
        ]
    )
    return candidates


def windows_helper_path() -> Path | None:
    for candidate in _windows_helper_candidates():
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _probe_windows_helper(helper: Path) -> dict[str, Any]:
    try:
        process = subprocess.run(
            [str(helper), "capabilities"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    if process.returncode != 0:
        return {}
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def detect_sandbox_capabilities() -> SandboxCapabilities:
    system = platform.system().lower()

    if system == "linux":
        bwrap = shutil.which("bwrap")
        if bwrap:
            return SandboxCapabilities(
                platform=system,
                backend="bubblewrap",
                os_isolation=True,
                process_isolation=True,
                network_isolation=True,
                filesystem_isolation=True,
                reason=(
                    "bubblewrap is available for process, filesystem, "
                    "and network isolation."
                ),
            )
        return SandboxCapabilities(
            platform=system,
            backend="logical",
            os_isolation=False,
            network_isolation=False,
            filesystem_isolation=False,
            reason=(
                "bubblewrap is not installed; Locdex policy enforcement "
                "remains active."
            ),
        )

    if system == "darwin":
        return SandboxCapabilities(
            platform=system,
            backend="logical",
            os_isolation=False,
            network_isolation=False,
            filesystem_isolation=False,
            reason=(
                "macOS keeps Locdex policy enforcement active. "
                "A hardened native process sandbox backend is not enabled yet."
            ),
        )

    if system == "windows":
        helper = windows_helper_path()
        if helper is not None:
            probe = _probe_windows_helper(helper)
            process_isolation = bool(probe.get("process_isolation", True))
            filesystem_isolation = bool(probe.get("filesystem_isolation", False))
            network_isolation = bool(probe.get("network_isolation", False))
            return SandboxCapabilities(
                platform=system,
                backend="windows-native",
                os_isolation=process_isolation,
                process_isolation=process_isolation,
                network_isolation=network_isolation,
                filesystem_isolation=filesystem_isolation,
                helper_path=str(helper),
                reason=(
                    "Locdex Windows native helper is available. Commands run "
                    "with a restricted token and Job Object process containment. "
                    "Filesystem and network restrictions remain enforced by "
                    "Locdex policy unless the helper explicitly reports native support."
                ),
            )
        return SandboxCapabilities(
            platform=system,
            backend="logical",
            os_isolation=False,
            network_isolation=False,
            filesystem_isolation=False,
            reason=(
                "Windows native helper is not installed; Locdex workspace/tool "
                "policy enforcement remains active. This is not AppContainer-grade "
                "filesystem or network isolation."
            ),
        )

    return SandboxCapabilities(
        platform=system or os.name,
        backend="logical",
        os_isolation=False,
        network_isolation=False,
        filesystem_isolation=False,
        reason="No supported OS sandbox backend was detected.",
    )


def sandbox_environment(mode: str | SandboxMode) -> dict[str, str]:
    profile = profile_for_mode(mode)
    env: dict[str, str] = {
        "LOCDEX_SANDBOX_MODE": profile.mode.value,
        "LOCDEX_SANDBOX_NETWORK": "1" if profile.network_access else "0",
    }

    if not profile.network_access:
        env.update(
            {
                "NO_PROXY": "*",
                "no_proxy": "*",
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
                "http_proxy": "http://127.0.0.1:9",
                "https_proxy": "http://127.0.0.1:9",
                "all_proxy": "http://127.0.0.1:9",
            }
        )

    return env


def _validated_working_directory(
    repo_path: str,
    cwd: str,
) -> tuple[Path, Path]:
    root = Path(repo_path).resolve()
    working = Path(cwd).resolve()
    try:
        working.relative_to(root)
    except ValueError as exc:
        raise ValueError("Sandbox cwd must remain inside the workspace.") from exc
    return root, working


def wrap_command(
    repo_path: str,
    cwd: str,
    argv: list[str],
    mode: str | SandboxMode,
) -> tuple[list[str], str]:
    profile = profile_for_mode(mode)
    capabilities = detect_sandbox_capabilities()

    if profile.mode is SandboxMode.UNRESTRICTED:
        return list(argv), capabilities.backend

    root, working = _validated_working_directory(repo_path, cwd)

    if capabilities.backend == "bubblewrap":
        command = [
            "bwrap",
            "--die-with-parent",
            "--new-session",
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
        ]

        if profile.workspace_write:
            command.extend(["--bind", str(root), str(root)])

        if not profile.network_access:
            command.append("--unshare-net")

        command.extend(["--chdir", str(working), "--"])
        command.extend(argv)
        return command, "bubblewrap"

    if capabilities.backend == "windows-native":
        helper = windows_helper_path()
        if helper is None:
            raise ValueError("Windows native sandbox helper is unavailable.")
        command = [
            str(helper),
            "run",
            "--workspace",
            str(root),
            "--cwd",
            str(working),
            "--mode",
            profile.mode.value,
            "--",
            *argv,
        ]
        return command, "windows-native"

    return list(argv), capabilities.backend
