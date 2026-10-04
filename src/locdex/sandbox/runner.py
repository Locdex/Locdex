from __future__ import annotations

import os
import platform
import shutil
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "backend": self.backend,
            "os_isolation": self.os_isolation,
            "network_isolation": self.network_isolation,
            "filesystem_isolation": self.filesystem_isolation,
            "reason": self.reason,
        }


def detect_sandbox_capabilities() -> SandboxCapabilities:
    system = platform.system().lower()

    if system == "linux":
        bwrap = shutil.which("bwrap")
        if bwrap:
            return SandboxCapabilities(
                platform=system,
                backend="bubblewrap",
                os_isolation=True,
                network_isolation=True,
                filesystem_isolation=True,
                reason="bubblewrap is available for process isolation.",
            )
        return SandboxCapabilities(
            platform=system,
            backend="logical",
            os_isolation=False,
            network_isolation=False,
            filesystem_isolation=False,
            reason="bubblewrap is not installed; Locdex policy enforcement remains active.",
        )

    if system == "darwin":
        return SandboxCapabilities(
            platform=system,
            backend="logical",
            os_isolation=False,
            network_isolation=False,
            filesystem_isolation=False,
            reason=(
                "macOS v1 keeps Locdex policy enforcement active. "
                "A hardened process sandbox backend is not enabled yet."
            ),
        )

    if system == "windows":
        return SandboxCapabilities(
            platform=system,
            backend="logical",
            os_isolation=False,
            network_isolation=False,
            filesystem_isolation=False,
            reason=(
                "Windows v1 uses Locdex workspace/tool policy enforcement. "
                "A stronger AppContainer/Job isolation backend can be added later."
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
        # This is defense in depth, not a claim of OS-level network isolation.
        # The sandbox policy also rejects known network-capable tools.
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

    if capabilities.backend != "bubblewrap":
        return list(argv), capabilities.backend

    root = Path(repo_path).resolve()
    working = Path(cwd).resolve()
    try:
        working.relative_to(root)
    except ValueError as exc:
        raise ValueError("Sandbox cwd must remain inside the workspace.") from exc

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
