from __future__ import annotations

from pathlib import Path
from typing import Any

from ..agent import AgentEngine
from ..events import AgentEvent, EventBus
from ..models import MODEL_PROFILES, selected_model_key
from ..sandbox import SandboxMode, detect_sandbox_capabilities
from ..security import (
    ApprovalChoice,
    PermissionController,
    PermissionMode,
    PermissionRequest,
)
from ..session import (
    ChangeSet,
    PersistentSteeringQueue,
    SessionState,
    SessionTask,
    create_checkpoint,
    list_checkpoints,
    list_sessions,
    load_checkpoint,
    undo_checkpoint,
)


def interactive_permission(request: PermissionRequest) -> ApprovalChoice:
    print()
    print("=" * 72)
    print(f"Permission required: {request.risk.value} | {request.tool}")
    print("-" * 72)
    print(request.preview)
    print("-" * 72)
    print("[y] allow once   [a] allow similar actions this session   [n] deny")
    while True:
        try:
            choice = input("Choice [y/a/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ApprovalChoice.DENY
        if choice in {"y", "yes"}:
            return ApprovalChoice.ALLOW_ONCE
        if choice in {"a", "always", "session"}:
            return ApprovalChoice.ALLOW_SESSION
        if choice in {"", "n", "no", "deny"}:
            return ApprovalChoice.DENY
        print("Enter y, a, or n.")


def _render_event(event: AgentEvent) -> None:
    data = event.data
    if event.kind == "tool.requested":
        tool = str(data.get("tool", "tool"))
        if tool in {"read_file", "list_files", "search_code", "find_symbol", "find_references"}:
            print(f"  ● {tool}")
        elif tool in {"run_tests", "run_command"}:
            print(f"  ◆ {tool}")
        elif tool.startswith("git_"):
            print(f"  ◆ {tool}")
        else:
            print(f"  ◆ {tool}")
    elif event.kind == "sandbox.denied":
        print(f"  ⛔ sandbox denied {data.get('tool')}: {data.get('reason')}")
    elif event.kind == "permission.denied":
        print(f"  ⛔ permission denied {data.get('tool')}")
    elif event.kind == "agent.stopped":
        print(f"  ■ agent stopped: {data.get('status')}")


def _session_context(state: SessionState) -> str:
    rows: list[str] = []
    if state.notes:
        rows.append("Persistent user/session notes:")
        rows.extend(f"- {note}" for note in state.notes[-12:])

    if state.tasks:
        rows.append("Recent completed/attempted tasks:")
        for item in state.tasks[-6:]:
            files = ", ".join(item.files_modified) if item.files_modified else "none"
            rows.append(
                f"- {item.status}: {item.task} | summary={item.summary} | "
                f"files={files} | verification={item.verification_passed}"
            )

    return "\n".join(rows)[-8000:]


def _print_header(state: SessionState) -> None:
    caps = detect_sandbox_capabilities()
    print()
    print("Locdex interactive")
    print(f"Session: {state.session_id}")
    print(f"Repository: {state.repo_path}")
    print(f"Model: {state.model}")
    print(f"Permissions: {state.permission_mode}")
    print(
        f"Sandbox: {state.sandbox_mode} "
        f"({caps.backend}; OS isolation={'yes' if caps.os_isolation else 'no'})"
    )
    print("Type /help for commands.")
    print()


def _help() -> None:
    print(
        """
Commands:
  /help                       Show this help.
  /status                     Show session/model/permission/sandbox status.
  /model [key]                Show or change the model.
  /permissions [mode]         plan | ask | auto-edit | trusted | unrestricted.
  /sandbox [mode]             read-only | workspace-write | workspace-network | unrestricted.
  /diff                       Show the latest completed ChangeSet diff.
  /checkpoints                List session checkpoints.
  /undo [checkpoint-id]       Undo a completed Locdex checkpoint if files have not diverged.
  /sessions                   List recent Locdex sessions.
  /note <text>                Persist a session constraint/note.
  /compact                    Deterministically compact older task history.
  /new                        Start a new session for this repository.
  /exit                       Save and exit.

Any other input is executed as a coding-agent task.
""".strip()
    )


def _compact_state(state: SessionState) -> None:
    if len(state.tasks) <= 6:
        print("Session history is already compact.")
        return
    older = state.tasks[:-6]
    summary = "; ".join(
        f"{item.status}:{item.task[:80]}"
        for item in older[-12:]
    )
    state.notes.append("Compacted earlier task history: " + summary)
    state.tasks = state.tasks[-6:]
    state.save()
    print(f"Compacted {len(older)} older task record(s).")


def _find_resume_session(repo_path: str, session_id: str | None) -> SessionState | None:
    if session_id:
        return SessionState.load(session_id)
    root = str(Path(repo_path).resolve())
    for state in list_sessions(limit=100):
        if str(Path(state.repo_path).resolve()) == root:
            return state
    return None


def run_interactive(
    repo_path: str = ".",
    *,
    resume_id: str | None = None,
) -> int:
    root = Path(repo_path).resolve()
    if not root.is_dir():
        print(f"Locdex session error: repository does not exist: {root}")
        return 1

    try:
        state = _find_resume_session(str(root), resume_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Locdex session error: {exc}")
        return 1

    if state is None:
        state = SessionState.create(
            repo_path=str(root),
            model=selected_model_key(),
        )
        state.save()

    _print_header(state)

    while True:
        try:
            raw = input("locdex> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            state.save()
            return 0

        if not raw:
            continue

        if raw.startswith("/"):
            command, _, remainder = raw.partition(" ")
            command = command.lower()
            value = remainder.strip()

            if command in {"/exit", "/quit"}:
                state.save()
                return 0
            if command == "/help":
                _help()
                continue
            if command == "/status":
                caps = detect_sandbox_capabilities()
                print(f"session={state.session_id}")
                print(f"repo={state.repo_path}")
                print(f"model={state.model}")
                print(f"permissions={state.permission_mode}")
                print(f"sandbox={state.sandbox_mode}")
                print(
                    f"sandbox_backend={caps.backend} "
                    f"os_isolation={caps.os_isolation} "
                    f"network_isolation={caps.network_isolation}"
                )
                print(f"tasks={len(state.tasks)} checkpoints={len(list_checkpoints(state.session_id))}")
                continue
            if command == "/model":
                if not value:
                    print(f"Current model: {state.model}")
                    print("Available: " + ", ".join(sorted(MODEL_PROFILES)))
                    continue
                key = value.lower()
                if key not in MODEL_PROFILES:
                    print("Unknown model. Available: " + ", ".join(sorted(MODEL_PROFILES)))
                    continue
                state.model = key
                state.save()
                print(f"Model set to {key}.")
                continue
            if command == "/permissions":
                if not value:
                    print(f"Permission mode: {state.permission_mode}")
                    continue
                try:
                    mode = PermissionMode(value)
                except ValueError:
                    print("Choose: " + ", ".join(mode.value for mode in PermissionMode))
                    continue
                state.permission_mode = mode.value
                state.save()
                print(f"Permission mode set to {mode.value}.")
                continue
            if command == "/sandbox":
                if not value:
                    print(f"Sandbox mode: {state.sandbox_mode}")
                    continue
                try:
                    mode = SandboxMode(value)
                except ValueError:
                    print("Choose: " + ", ".join(mode.value for mode in SandboxMode))
                    continue
                state.sandbox_mode = mode.value
                state.save()
                print(f"Sandbox mode set to {mode.value}.")
                continue
            if command == "/diff":
                print(state.latest_diff or "No completed ChangeSet diff in this session.")
                continue
            if command == "/checkpoints":
                rows = list_checkpoints(state.session_id)
                if not rows:
                    print("No checkpoints.")
                for row in rows:
                    print(
                        f"{row.checkpoint_id} | {row.created_at} | "
                        f"{len(row.files)} file(s) | {row.task[:80]}"
                    )
                continue
            if command == "/undo":
                checkpoint_id = value or state.latest_checkpoint_id
                if not checkpoint_id:
                    print("No checkpoint available to undo.")
                    continue
                try:
                    checkpoint = load_checkpoint(state.session_id, checkpoint_id)
                    outcome = undo_checkpoint(checkpoint)
                except (FileNotFoundError, ValueError) as exc:
                    print(f"Undo failed: {exc}")
                    continue
                if outcome["ok"]:
                    print("Restored: " + ", ".join(outcome["restored"]))
                    state.add_note(f"Checkpoint {checkpoint_id} was undone.")
                    state.save()
                else:
                    print(
                        "Undo stopped because files diverged: "
                        + ", ".join(outcome["conflicts"])
                    )
                    print("Review those files before forcing any restore.")
                continue
            if command == "/sessions":
                for item in list_sessions(limit=20):
                    marker = "*" if item.session_id == state.session_id else " "
                    print(
                        f"{marker} {item.session_id} | {item.updated_at} | "
                        f"{item.model} | {item.repo_path}"
                    )
                continue
            if command == "/note":
                if not value:
                    print("Usage: /note <persistent constraint or reminder>")
                    continue
                state.add_note(value)
                state.save()
                print("Session note saved.")
                continue
            if command == "/compact":
                _compact_state(state)
                continue
            if command == "/new":
                state.save()
                state = SessionState.create(
                    repo_path=state.repo_path,
                    model=state.model,
                    permission_mode=state.permission_mode,
                    sandbox_mode=state.sandbox_mode,
                )
                state.save()
                _print_header(state)
                continue

            print(f"Unknown command: {command}. Type /help.")
            continue

        steering_queue = PersistentSteeringQueue(state.session_id)
        steering_queue.reset_cancel()
        # Drain stale steering left from a previous completed run. New messages
        # submitted after execution begins are consumed between model turns.
        steering_queue.drain()

        permission_controller = PermissionController(
            state.permission_mode,
            approval_callback=(
                interactive_permission
                if state.permission_mode == PermissionMode.ASK.value
                else None
            ),
        )
        bus = EventBus()
        bus.subscribe(_render_event)
        engine = AgentEngine(model_key=state.model)

        print()
        try:
            result = engine.execute(
                raw,
                state.repo_path,
                max_steps=12,
                routing_mode="balanced",
                permission_controller=permission_controller,
                sandbox_mode=state.sandbox_mode,
                event_bus=bus,
                additional_context=_session_context(state),
                steering_queue=steering_queue,
                progress=None,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Locdex agent error: {exc}")
            continue

        changeset = ChangeSet.from_result(result)
        checkpoint_id: str | None = None
        if result.get("status") == "completed" and changeset.files:
            checkpoint = create_checkpoint(
                session_id=state.session_id,
                repo_path=state.repo_path,
                journal_payload=engine.change_journal.checkpoint_payload(),
                task=raw,
            )
            if checkpoint is not None:
                checkpoint_id = checkpoint.checkpoint_id

        state.latest_diff = changeset.diff
        state.add_task(
            SessionTask(
                task=raw,
                status=str(result.get("status", "unknown")),
                model=state.model,
                sandbox_mode=state.sandbox_mode,
                permission_mode=state.permission_mode,
                summary=str(result.get("summary", "")),
                files_modified=list(changeset.files),
                verification_passed=changeset.verification_passed,
                checkpoint_id=checkpoint_id,
            )
        )
        state.save()

        print()
        print(str(result.get("summary") or "Task finished."))
        print(changeset.render_summary())
        if checkpoint_id:
            print(f"Checkpoint: {checkpoint_id}")
        print()
