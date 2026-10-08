from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..events import AgentEvent

SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
STEP_RE = re.compile(r"Step\s+(\d+)/(\d+)", re.IGNORECASE)
READ_TOOLS = {
    "read_file": "Reading",
    "list_files": "Listing files",
    "search_code": "Searching code",
    "find_symbol": "Finding symbol",
    "find_references": "Finding references",
    "get_symbol_source": "Reading symbol",
    "get_reference_context": "Reading references",
    "related_files": "Finding related files",
}
WRITE_TOOLS = {
    "write_file": "Writing",
    "replace_in_file": "Editing",
    "replace_symbol": "Editing symbol",
    "insert_after_symbol": "Inserting code",
    "delete_path": "Deleting",
}


def _safe_path(args: dict) -> str:
    value = args.get("path")
    if not isinstance(value, str) or not value:
        return ""
    # Display only a short path, never an input, patch, or file body.
    cleaned = value.replace("\\", "/").strip()
    return cleaned[:90] + "…" if len(cleaned) > 90 else cleaned


def describe_tool(tool: str, args: dict | None = None) -> str:
    args = args if isinstance(args, dict) else {}
    path = _safe_path(args)
    if tool in READ_TOOLS:
        label = READ_TOOLS[tool]
    elif tool in WRITE_TOOLS:
        label = WRITE_TOOLS[tool]
    elif tool == "run_tests":
        label = "Running tests"
    elif tool == "run_command":
        argv = args.get("argv")
        label = "Running " + str(argv[0])[:40] if isinstance(argv, list) and argv else "Running command"
    elif tool.startswith("git_"):
        label = "Git " + tool[4:].replace("_", " ")
    elif tool.startswith("mcp_"):
        label = "External tool " + tool
    else:
        label = "Using " + tool[:48]
    return f"{label}: {path}" if path else label


@dataclass
class ActivityState:
    started: float = field(default_factory=time.monotonic)
    phase: str = "Preparing workspace"
    step: int = 0
    max_steps: int = 0
    tools_started: int = 0
    tools_completed: int = 0
    current_tool: str | None = None

    def on_progress(self, message: str) -> str | None:
        match = STEP_RE.search(message)
        if match:
            self.step, self.max_steps = int(match.group(1)), int(match.group(2))
            self.phase = "Choosing next action"
            return f"Step {self.step}/{self.max_steps} · Choosing next action"
        if "[Agent] verify" in message:
            self.phase = "Verifying changes"
            return "Verifying changes"
        if message.startswith("[Router]"):
            self.phase = "Switching model"
            return "Switching to configured model"
        return None

    def on_event(self, event: AgentEvent) -> str | None:
        kind, data = event.kind, event.data
        if kind == "agent.started":
            self.phase = "Preparing context"
            return "Preparing context"
        if kind == "tool.requested":
            tool = str(data.get("tool", "tool"))
            self.current_tool = tool
            self.tools_started += 1
            self.phase = describe_tool(tool, data.get("args"))
            return "→ " + self.phase
        if kind == "tool.completed":
            tool = str(data.get("tool", "tool"))
            self.tools_completed += 1
            self.current_tool = None
            result = data.get("result")
            failed = isinstance(result, dict) and (
                result.get("ok") is False
                or "error" in result
                or result.get("permission_denied")
                or result.get("sandbox_denied")
            )
            self.phase = "Re-evaluating result" if failed else "Choosing next action"
            return ("✗ " if failed else "✓ ") + describe_tool(tool)
        if kind == "sandbox.denied":
            self.phase = "Blocked by sandbox"
            return "✗ Sandbox blocked " + str(data.get("tool", "tool"))[:48]
        if kind == "permission.denied":
            self.phase = "Permission denied"
            return "✗ Permission denied for " + str(data.get("tool", "tool"))[:48]
        if kind in {"agent.completed", "agent.stopped"}:
            self.phase = "Finished"
            return "■ " + str(data.get("status", "finished"))[:24]
        return None

    def toolbar(self, frame: int | None = None) -> str:
        elapsed = max(0, int(time.monotonic() - self.started))
        spinner = SPINNER[
            (frame if frame is not None else int(time.monotonic() * 8)) % len(SPINNER)
        ]
        step = f"  {self.step}/{self.max_steps}" if self.max_steps else ""
        return (
            f" {spinner} {self.phase[:74]}{step}  · {elapsed}s  · "
            f"{self.tools_completed} tools  · Enter to steer /cancel to stop"
        )
