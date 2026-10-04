from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChangeSet:
    files: tuple[str, ...] = ()
    diff: str = ""
    verification: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> "ChangeSet":
        return cls(
            files=tuple(str(path) for path in result.get("files_modified") or []),
            diff=str(result.get("diff") or ""),
            verification=dict(result.get("verification") or {}),
            summary=str(result.get("summary") or ""),
        )

    @property
    def verification_passed(self) -> bool | None:
        if not self.verification:
            return None
        value = self.verification.get("passed")
        return bool(value) if value is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "diff": self.diff,
            "verification": dict(self.verification),
            "summary": self.summary,
        }

    def render_summary(self) -> str:
        if not self.files:
            return "No workspace files changed."
        verification = self.verification_passed
        suffix = (
            "verification passed"
            if verification is True
            else "verification failed"
            if verification is False
            else "verification not recorded"
        )
        return f"{len(self.files)} file(s) changed | {suffix}: " + ", ".join(self.files)
