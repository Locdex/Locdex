from __future__ import annotations

from dataclasses import dataclass, field

from .security.secrets import redact_secrets


def _safe_text(value: str, limit: int = 1200) -> str:
    text, _ = redact_secrets(str(value))
    return text.strip()[:limit]


def _add_unique(items: list[str], value: str, *, limit: int = 32) -> None:
    cleaned = _safe_text(value, 500)
    if cleaned and cleaned not in items:
        items.append(cleaned)
    if len(items) > limit:
        del items[:-limit]


@dataclass
class TaskState:
    """Durable task metadata. Never stores source code or raw tool transcripts."""

    objective: str
    acceptance_criteria: list[str] = field(default_factory=list)
    pinned_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    failing_checks: list[str] = field(default_factory=list)
    last_validation_status: str | None = None
    validation_stale: bool = False
    next_action: str | None = None
    compactions: int = 0

    @classmethod
    def from_task(
        cls,
        objective: str,
        acceptance_criteria: list[str] | None = None,
    ) -> "TaskState":
        return cls(
            objective=_safe_text(objective, 2400),
            acceptance_criteria=[
                _safe_text(item, 600)
                for item in (acceptance_criteria or [])
                if _safe_text(item, 600)
            ],
        )

    def pin_file(self, path: str) -> None:
        normalized = str(path).replace("\\", "/").strip()
        if normalized and normalized not in self.pinned_files:
            self.pinned_files.append(normalized)
        self.pinned_files = self.pinned_files[-40:]

    def drop_file(self, path: str) -> None:
        normalized = str(path).replace("\\", "/").strip()
        self.pinned_files = [item for item in self.pinned_files if item != normalized]

    def mark_modified(self, path: str) -> None:
        normalized = str(path).replace("\\", "/").strip()
        if not normalized:
            return
        if normalized not in self.modified_files:
            self.modified_files.append(normalized)
        self.modified_files = self.modified_files[-40:]
        self.pin_file(normalized)
        if self.last_validation_status is not None:
            self.validation_stale = True
        self.next_action = "validate modified workspace"

    def add_decision(self, decision: str) -> None:
        _add_unique(self.decisions, decision, limit=20)

    def add_open_question(self, question: str) -> None:
        _add_unique(self.open_questions, question, limit=12)

    def record_failure(self, check: str) -> None:
        _add_unique(self.failing_checks, check, limit=16)
        self.last_validation_status = "failed"
        self.validation_stale = False
        self.next_action = "diagnose latest failing check"

    def mark_validation(self, passed: bool, details: str | None = None) -> None:
        self.last_validation_status = "passed" if passed else "failed"
        self.validation_stale = False
        if passed:
            self.failing_checks.clear()
            self.next_action = "finish if acceptance criteria are satisfied"
        elif details:
            self.record_failure(details)
        else:
            self.next_action = "diagnose validation failure"

    def set_next_action(self, action: str | None) -> None:
        self.next_action = _safe_text(action, 500) if action else None

    def note_compaction(self) -> None:
        self.compactions += 1

    def to_prompt(self) -> str:
        lines = [
            "CURRENT TASK STATE",
            "",
            "Objective:",
            self.objective or "-",
            "",
            "Acceptance criteria:",
        ]
        lines.extend(f"- {item}" for item in self.acceptance_criteria or ["(none explicitly recorded)"])
        lines.extend(["", "Pinned files:"])
        lines.extend(f"- {item}" for item in self.pinned_files or ["(none)"])
        lines.extend(["", "Modified files:"])
        lines.extend(f"- {item}" for item in self.modified_files or ["(none)"])
        lines.extend(["", "Locked decisions:"])
        lines.extend(f"- {item}" for item in self.decisions or ["(none)"])
        lines.extend(["", "Open questions:"])
        lines.extend(f"- {item}" for item in self.open_questions or ["(none)"])
        lines.extend(["", "Current failures:"])
        lines.extend(f"- {item}" for item in self.failing_checks or ["(none)"])
        lines.extend(
            [
                "",
                f"Last validation: {self.last_validation_status or 'not run'}",
                f"Validation stale: {'yes' if self.validation_stale else 'no'}",
                f"Next action: {self.next_action or '(not set)'}",
                "",
                "File contents are retrievable context. Re-read a pinned file when exact source is needed.",
            ]
        )
        return "\n".join(lines)
