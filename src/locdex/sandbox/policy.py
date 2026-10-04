from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..security import RiskClass


class SandboxMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    WORKSPACE_NETWORK = "workspace-network"
    UNRESTRICTED = "unrestricted"


@dataclass(frozen=True)
class SandboxDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class SandboxProfile:
    mode: SandboxMode
    workspace_write: bool
    command_execution: bool
    network_access: bool
    git_write: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "workspace_write": self.workspace_write,
            "command_execution": self.command_execution,
            "network_access": self.network_access,
            "git_write": self.git_write,
        }


def profile_for_mode(mode: str | SandboxMode) -> SandboxProfile:
    normalized = SandboxMode(mode)
    if normalized is SandboxMode.READ_ONLY:
        return SandboxProfile(
            mode=normalized,
            workspace_write=False,
            command_execution=False,
            network_access=False,
            git_write=False,
        )
    if normalized is SandboxMode.WORKSPACE_WRITE:
        return SandboxProfile(
            mode=normalized,
            workspace_write=True,
            command_execution=True,
            network_access=False,
            git_write=True,
        )
    if normalized is SandboxMode.WORKSPACE_NETWORK:
        return SandboxProfile(
            mode=normalized,
            workspace_write=True,
            command_execution=True,
            network_access=True,
            git_write=True,
        )
    return SandboxProfile(
        mode=normalized,
        workspace_write=True,
        command_execution=True,
        network_access=True,
        git_write=True,
    )


class SandboxPolicy:
    def __init__(self, mode: str | SandboxMode = SandboxMode.WORKSPACE_WRITE):
        self.profile = profile_for_mode(mode)

    @property
    def mode(self) -> SandboxMode:
        return self.profile.mode

    def authorize(
        self,
        *,
        tool: str,
        risk: RiskClass,
        args: dict[str, Any],
    ) -> SandboxDecision:
        if risk is RiskClass.DANGEROUS:
            return SandboxDecision(False, "Dangerous tools are blocked by the sandbox.")

        if risk is RiskClass.WRITE and not self.profile.workspace_write:
            return SandboxDecision(
                False,
                f"Sandbox mode {self.mode.value!r} is read-only.",
            )

        if risk is RiskClass.EXECUTE and not self.profile.command_execution:
            return SandboxDecision(
                False,
                f"Sandbox mode {self.mode.value!r} does not allow command execution.",
            )

        if risk is RiskClass.GIT_WRITE and not self.profile.git_write:
            return SandboxDecision(
                False,
                f"Sandbox mode {self.mode.value!r} does not allow Git mutations.",
            )

        if risk is RiskClass.NETWORK and not self.profile.network_access:
            return SandboxDecision(
                False,
                f"Sandbox mode {self.mode.value!r} blocks network access.",
            )

        if tool in {"git_pull", "git_push"} and not self.profile.network_access:
            return SandboxDecision(
                False,
                f"Sandbox mode {self.mode.value!r} blocks remote Git/network access.",
            )

        if tool == "run_command":
            argv = args.get("argv") or []
            executable = str(argv[0]).lower() if isinstance(argv, list) and argv else ""
            network_tools = {
                "curl",
                "wget",
                "ssh",
                "scp",
                "ftp",
                "nc",
                "ncat",
                "npm",
                "pnpm",
                "yarn",
                "pip",
                "pip3",
            }
            if (
                executable.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                in network_tools
                and not self.profile.network_access
            ):
                return SandboxDecision(
                    False,
                    f"Sandbox mode {self.mode.value!r} blocks network-capable command {executable!r}.",
                )

        return SandboxDecision(True, f"Allowed by sandbox mode {self.mode.value!r}.")
