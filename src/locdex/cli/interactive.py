from __future__ import annotations

import asyncio
import os
import queue
import signal
import time
from pathlib import Path
from collections import deque
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from ..agent import AgentEngine
from .activity import ActivityState
from ..events import AgentEvent, EventBus
from ..models import MODEL_PROFILES, selected_model_key
from ..runtime.isolated import IsolatedLlamaCppSession
from ..routing.execution import execute_with_escalation
from ..sandbox import SandboxMode, detect_sandbox_capabilities
from ..security import (
    ApprovalChoice,
    PermissionController,
    PermissionMode,
    PermissionRequest,
    format_permission_details,
    format_permission_request,
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


def _parse_approval(value: str) -> ApprovalChoice | None:
    choice = value.strip().lower()
    if choice in {"y", "yes"}:
        return ApprovalChoice.ALLOW_ONCE
    if choice in {"a", "always", "session"}:
        return ApprovalChoice.ALLOW_SESSION
    if choice in {"", "n", "no", "deny"}:
        return ApprovalChoice.DENY
    return None


def interactive_permission(
    request: PermissionRequest,
) -> ApprovalChoice:
    print()
    print(format_permission_request(request))
    print("[y] once  [a] similar this session  [d] details  [N] deny")
    while True:
        try:
            raw = input("Choice [y/a/d/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ApprovalChoice.DENY
        if raw in {"d", "details", "show"}:
            print()
            print(format_permission_details(request))
            print()
            continue
        parsed = _parse_approval(raw)
        if parsed is not None:
            return parsed
        print("Enter y, a, d, or n.")


class _ApprovalBroker:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.pending: asyncio.Queue[
            tuple[PermissionRequest, queue.Queue[ApprovalChoice]]
        ] = asyncio.Queue()

    def request(
        self,
        request: PermissionRequest,
    ) -> ApprovalChoice:
        response: queue.Queue[ApprovalChoice] = queue.Queue(maxsize=1)
        future = asyncio.run_coroutine_threadsafe(
            self.pending.put((request, response)),
            self.loop,
        )
        future.result()
        return response.get()

    @staticmethod
    def resolve(
        response: queue.Queue[ApprovalChoice],
        choice: ApprovalChoice,
    ) -> None:
        response.put(choice)


def _render_event(event: AgentEvent) -> None:
    data = event.data
    if event.kind == "tool.requested":
        tool = str(data.get("tool", "tool"))
        if tool in {
            "read_file",
            "list_files",
            "search_code",
            "find_symbol",
            "find_references",
        }:
            print(f"  ● {tool}")
        else:
            print(f"  ◆ {tool}")
    elif event.kind == "sandbox.denied":
        print(
            f"  ⛔ sandbox denied {data.get('tool')}: "
            f"{data.get('reason')}"
        )
    elif event.kind == "permission.denied":
        print(
            f"  ⛔ permission denied {data.get('tool')}"
        )
    elif event.kind == "agent.stopped":
        print(
            f"  ■ agent stopped: {data.get('status')}"
        )


def _session_context(state: SessionState) -> str:
    rows: list[str] = []
    if state.notes:
        rows.append("Persistent user/session notes:")
        rows.extend(
            f"- {note}"
            for note in state.notes[-12:]
        )

    if state.tasks:
        rows.append("Recent completed/attempted tasks:")
        for item in state.tasks[-6:]:
            files = (
                ", ".join(item.files_modified)
                if item.files_modified
                else "none"
            )
            rows.append(
                f"- {item.status}: {item.task} | "
                f"summary={item.summary} | "
                f"files={files} | "
                f"verification={item.verification_passed}"
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
        f"({caps.backend}; "
        f"OS isolation={'yes' if caps.os_isolation else 'no'})"
    )
    print("Type /help for commands; exit or /exit closes Locdex.")
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
  /undo [checkpoint-id]       Undo a completed checkpoint if files have not diverged.
  /sessions                   List recent Locdex sessions.
  /note <text>                Persist a session constraint/note.
  /compact                    Deterministically compact older task history.
  /new                        Start a new session for this repository.
  exit | quit | /exit         Save and exit. During a task, cancel then exit.

During an active agent run:
  type text                    Steer the active agent in the same terminal.
  /cancel or Ctrl+C           Request cancellation; Ctrl+C again force-exits.
  /status                     Show the current session and execution policy.

Any other idle input is executed as a coding-agent task.
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
    state.notes.append(
        "Compacted earlier task history: " + summary
    )
    state.tasks = state.tasks[-6:]
    state.save()
    print(
        f"Compacted {len(older)} older task record(s)."
    )


def _find_resume_session(
    repo_path: str,
    session_id: str | None,
) -> SessionState | None:
    if session_id:
        return SessionState.load(session_id)
    root = str(Path(repo_path).resolve())
    for state in list_sessions(limit=100):
        if str(Path(state.repo_path).resolve()) == root:
            return state
    return None


def _print_active_status(state: SessionState) -> None:
    caps = detect_sandbox_capabilities()
    print(
        f"session={state.session_id} "
        f"model={state.model} "
        f"permissions={state.permission_mode} "
        f"sandbox={state.sandbox_mode} "
        f"backend={caps.backend}"
    )


def _is_exit_command(value: str) -> bool:
    return value.strip().casefold() in {
        "exit", "quit", "/exit", "/quit", ":q",
    }


class _InterruptState:
    """A cooperative interrupt first; emergency process exit on repeated Ctrl+C.

    Force-exit deliberately skips rollback only if the user explicitly repeats
    the interrupt. It is not used for ordinary /cancel or /exit.
    """

    def __init__(self) -> None:
        self.last_interrupt = 0.0
        self.count = 0

    def press(self, *, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        if self.count and moment - self.last_interrupt < 0.4:
            # Avoid treating one terminal keypress, dispatched through both
            # a signal handler and prompt-toolkit, as a double interrupt.
            return False
        self.count = self.count + 1 if moment - self.last_interrupt < 4.0 else 1
        self.last_interrupt = moment
        return self.count >= 2


async def _active_task(
    state: SessionState,
    raw: str,
) -> tuple[dict[str, Any] | None, AgentEngine | None, bool]:
    loop = asyncio.get_running_loop()
    broker = _ApprovalBroker(loop)
    steering_queue = PersistentSteeringQueue(state.session_id)
    steering_queue.reset_cancel()
    steering_queue.drain()

    permission_controller = PermissionController(
        state.permission_mode,
        approval_callback=broker.request,
    )
    bus = EventBus()
    activity = ActivityState()
    updates: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def post(kind: str, value: Any) -> None:
        loop.call_soon_threadsafe(updates.put_nowait, (kind, value))

    bus.subscribe(lambda event: post("event", event))
    engine = AgentEngine(model_key=state.model)

    def execute() -> dict[str, Any]:
        local_session = IsolatedLlamaCppSession(
            model_key=state.model,
            cancelled=lambda: steering_queue.cancelled,
            progress=lambda message: post("progress", message),
        )
        try:
            return execute_with_escalation(
                engine,
                raw,
                state.repo_path,
                max_steps=12,
                routing_mode="balanced",
                permission_controller=permission_controller,
                sandbox_mode=state.sandbox_mode,
                event_bus=bus,
                additional_context=_session_context(state),
                steering_queue=steering_queue,
                progress=lambda message: post("progress", message),
                local_session=local_session,
            )
        finally:
            local_session.close()

    worker = loop.run_in_executor(None, execute)
    pending_request: tuple[
        PermissionRequest, queue.Queue[ApprovalChoice]
    ] | None = None
    exit_after = False
    interrupt_state = _InterruptState()

    recent_actions: deque[str] = deque(maxlen=4)

    def prompt_message() -> str:
        """The entire live status belongs above the editor, not in a bottom bar."""
        status = activity.toolbar().split(" · Enter to steer")[0].strip()
        rows = [f"\n  {status}"]
        rows.extend(f"  {line}" for line in recent_actions)
        if pending_request is not None:
            request, _ = pending_request
            rows.extend([
                "",
                "  ┌─ Permission required ───────────────────────────",
                "  │ " + format_permission_request(request),
                "  │",
                "  │ [y] Allow once       [a] Allow similar this session",
                "  │ [d] Show details     [n] Deny",
                "  └──────────────────────────────────────────────────",
                "  Choice › ",
            ])
        else:
            rows.extend([
                "",
                "  Enter instructions to steer  ·  /cancel to stop  ·  exit to close",
                "  locdex › ",
            ])
        return "\n".join(rows)

    prompt = PromptSession(
        message=prompt_message,
        refresh_interval=0.2,
    )

    def reject_pending_permission() -> None:
        nonlocal pending_request
        if pending_request is not None:
            _, response = pending_request
            broker.resolve(response, ApprovalChoice.DENY)
            pending_request = None

    def cancel_active() -> None:
        steering_queue.cancel()
        reject_pending_permission()
        activity.phase = "Cancellation requested"
        print("Cancellation requested; waiting for the current operation to stop.")

    def interrupt() -> None:
        if interrupt_state.press():
            print(
                "\nEmergency exit requested. WARNING: an interrupted "
                "operation may not be rolled back.",
                flush=True,
            )
            # An in-process native inference call cannot always be interrupted
            # from Python. A repeated explicit Ctrl+C must let the user escape.
            os._exit(130)
        cancel_active()

    previous_sigint = None
    try:
        previous_sigint = signal.getsignal(signal.SIGINT)

        def on_sigint(_signum: int, _frame: Any) -> None:
            # Dispatch on the loop; never modify broker queues from a signal
            # handler or raise KeyboardInterrupt into asyncio's shutdown path.
            loop.call_soon_threadsafe(interrupt)

        signal.signal(signal.SIGINT, on_sigint)
    except ValueError:
        # Non-main-thread integrations cannot register OS signal handlers.
        previous_sigint = None

    print()
    print("Locdex is working. Activity, permissions and progress appear above the input.")
    input_task: asyncio.Task | None = None
    approval_task: asyncio.Task | None = None
    event_task: asyncio.Task | None = None

    try:
        with patch_stdout():
            while not worker.done():
                if input_task is None:
                    input_task = asyncio.create_task(
                        prompt.prompt_async()
                    )
                if approval_task is None and pending_request is None:
                    approval_task = asyncio.create_task(
                        broker.pending.get()
                    )
                if event_task is None:
                    event_task = asyncio.create_task(updates.get())

                waitables = {worker, input_task, event_task}
                if approval_task is not None:
                    waitables.add(approval_task)
                done, _ = await asyncio.wait(
                    waitables,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if worker in done:
                    break

                if event_task in done:
                    kind, value = event_task.result()
                    event_task = None
                    description = (
                        activity.on_event(value)
                        if kind == "event"
                        else activity.on_progress(str(value))
                    )
                    if description:
                        recent_actions.append(description)
                        if prompt.app is not None:
                            prompt.app.invalidate()

                if approval_task is not None and approval_task in done:
                    pending_request = approval_task.result()
                    approval_task = None
                    activity.phase = "Waiting for approval"
                    # Approval content is rendered inside the dynamic prompt
                    # above the input. Avoid printing while prompt-toolkit owns
                    # the terminal; it can erase important text on Windows.
                    # Leave the *existing* prompt running. Cancelling
                    # prompt_async while changing prompts can deadlock on
                    # Windows Terminal. A callable updates the prompt label.
                    if prompt.app is not None:
                        prompt.app.invalidate()

                if input_task is not None and input_task in done:
                    try:
                        message = input_task.result().strip()
                    except (EOFError, KeyboardInterrupt):
                        message = "/cancel"
                        was_interrupted = True
                    else:
                        was_interrupted = False
                    input_task = None

                    if was_interrupted:
                        interrupt()
                        continue

                    if pending_request is not None:
                        request, response = pending_request
                        if message.lower() in {"d", "details", "show"}:
                            print()
                            print(format_permission_details(request))
                            print()
                            continue
                        if _is_exit_command(message):
                            exit_after = True
                            cancel_active()
                            continue
                        if message.lower() in {"/cancel", "cancel"}:
                            cancel_active()
                            continue
                        parsed = _parse_approval(message)
                        if parsed is None:
                            recent_actions.append("Approval pending: y / a / d / n")
                            if prompt.app is not None:
                                prompt.app.invalidate()
                            continue
                        broker.resolve(response, parsed)
                        recent_actions.append(
                            "✓ Approved: " + format_permission_request(request)
                            if parsed is not ApprovalChoice.DENY
                            else "✗ Denied: " + format_permission_request(request)
                        )
                        pending_request = None
                        activity.phase = "Resuming model/tool execution"
                        if prompt.app is not None:
                            prompt.app.invalidate()
                        continue

                    if not message:
                        continue
                    if _is_exit_command(message):
                        exit_after = True
                        cancel_active()
                        continue
                    if message.lower() in {"/cancel", "cancel"}:
                        cancel_active()
                        continue
                    if message.lower() == "/status":
                        _print_active_status(state)
                        print(activity.toolbar())
                        continue
                    if message.lower() in {"/help", "/?"}:
                        print(
                            "While working: enter steering text, /status, "
                            "/cancel, or exit. Ctrl+C requests cancellation; "
                            "press again for emergency termination.",
                        )
                        continue
                    if message.startswith("/"):
                        print(
                            "That command is available after this task. "
                            "Use /cancel first to change execution policy.",
                        )
                        continue
                    steering_queue.submit(message)
                    print("Steering queued for the active run.")
    finally:
        reject_pending_permission()
        for pending in (input_task, approval_task, event_task):
            if pending is not None and not pending.done():
                pending.cancel()
        await asyncio.gather(
            *(
                pending
                for pending in (input_task, approval_task, event_task)
                if pending is not None
            ),
            return_exceptions=True,
        )
        if previous_sigint is not None:
            try:
                signal.signal(signal.SIGINT, previous_sigint)
            except ValueError:
                pass
    try:
        return await worker, engine, exit_after
    except Exception as exc:  # noqa: BLE001
        print(f"Locdex agent error: {exc}")
        return None, engine, exit_after


def _record_result(
    state: SessionState,
    raw: str,
    result: dict[str, Any],
    engine: AgentEngine,
) -> None:
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
    print(
        str(result.get("summary") or "Task finished.")
    )
    print(changeset.render_summary())
    if result.get("route") == "cloud":
        print(
            "Route: configured cloud fallback "
            f"({result.get('cloud_provider')}/"
            f"{result.get('cloud_model')})"
        )
    elif result.get("cloud_escalation", {}).get("reason"):
        print(
            "Cloud fallback: "
            + str(result["cloud_escalation"]["reason"])
        )
    if checkpoint_id:
        print(f"Checkpoint: {checkpoint_id}")
    print()


def run_interactive(
    repo_path: str = ".",
    *,
    resume_id: str | None = None,
) -> int:
    root = Path(repo_path).resolve()
    if not root.is_dir():
        print(
            f"Locdex session error: repository does not exist: "
            f"{root}"
        )
        return 1

    try:
        state = _find_resume_session(
            str(root),
            resume_id,
        )
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

        if _is_exit_command(raw):
            state.save()
            return 0

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
                print(
                    f"permissions={state.permission_mode}"
                )
                print(f"sandbox={state.sandbox_mode}")
                print(
                    f"sandbox_backend={caps.backend} "
                    f"os_isolation={caps.os_isolation} "
                    f"process_isolation={caps.process_isolation} "
                    f"network_isolation={caps.network_isolation}"
                )
                print(
                    f"tasks={len(state.tasks)} "
                    f"checkpoints="
                    f"{len(list_checkpoints(state.session_id))}"
                )
                continue
            if command == "/model":
                if not value:
                    print(f"Current model: {state.model}")
                    print(
                        "Available: "
                        + ", ".join(
                            sorted(MODEL_PROFILES)
                        )
                    )
                    continue
                key = value.lower()
                if key not in MODEL_PROFILES:
                    print(
                        "Unknown model. Available: "
                        + ", ".join(
                            sorted(MODEL_PROFILES)
                        )
                    )
                    continue
                state.model = key
                state.save()
                print(f"Model set to {key}.")
                continue
            if command == "/permissions":
                if not value:
                    print(
                        f"Permission mode: "
                        f"{state.permission_mode}"
                    )
                    continue
                try:
                    mode = PermissionMode(value)
                except ValueError:
                    print(
                        "Choose: "
                        + ", ".join(
                            item.value
                            for item in PermissionMode
                        )
                    )
                    continue
                state.permission_mode = mode.value
                state.save()
                print(
                    f"Permission mode set to "
                    f"{mode.value}."
                )
                continue
            if command == "/sandbox":
                if not value:
                    print(
                        f"Sandbox mode: "
                        f"{state.sandbox_mode}"
                    )
                    continue
                try:
                    mode = SandboxMode(value)
                except ValueError:
                    print(
                        "Choose: "
                        + ", ".join(
                            item.value
                            for item in SandboxMode
                        )
                    )
                    continue
                state.sandbox_mode = mode.value
                state.save()
                print(
                    f"Sandbox mode set to "
                    f"{mode.value}."
                )
                continue
            if command == "/diff":
                print(
                    state.latest_diff
                    or "No completed ChangeSet diff "
                    "in this session."
                )
                continue
            if command == "/checkpoints":
                rows = list_checkpoints(
                    state.session_id
                )
                if not rows:
                    print("No checkpoints.")
                for row in rows:
                    print(
                        f"{row.checkpoint_id} | "
                        f"{row.created_at} | "
                        f"{len(row.files)} file(s) | "
                        f"{row.task[:80]}"
                    )
                continue
            if command == "/undo":
                checkpoint_id = (
                    value
                    or state.latest_checkpoint_id
                )
                if not checkpoint_id:
                    print(
                        "No checkpoint available to undo."
                    )
                    continue
                try:
                    checkpoint = load_checkpoint(
                        state.session_id,
                        checkpoint_id,
                    )
                    outcome = undo_checkpoint(checkpoint)
                except (
                    FileNotFoundError,
                    ValueError,
                ) as exc:
                    print(f"Undo failed: {exc}")
                    continue
                if outcome["ok"]:
                    print(
                        "Restored: "
                        + ", ".join(outcome["restored"])
                    )
                    state.add_note(
                        f"Checkpoint {checkpoint_id} "
                        "was undone."
                    )
                    state.save()
                else:
                    print(
                        "Undo stopped because files diverged: "
                        + ", ".join(
                            outcome["conflicts"]
                        )
                    )
                    print(
                        "Review those files before forcing "
                        "any restore."
                    )
                continue
            if command == "/sessions":
                for item in list_sessions(limit=20):
                    marker = (
                        "*"
                        if item.session_id
                        == state.session_id
                        else " "
                    )
                    print(
                        f"{marker} {item.session_id} | "
                        f"{item.updated_at} | "
                        f"{item.model} | "
                        f"{item.repo_path}"
                    )
                continue
            if command == "/note":
                if not value:
                    print(
                        "Usage: /note <persistent "
                        "constraint or reminder>"
                    )
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

            print(
                f"Unknown command: {command}. "
                "Type /help."
            )
            continue

        result, engine, exit_after = asyncio.run(
            _active_task(state, raw)
        )
        if result is not None and engine is not None:
            _record_result(
                state,
                raw,
                result,
                engine,
            )
        if exit_after:
            state.save()
            return 0
