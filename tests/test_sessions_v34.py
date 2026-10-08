from __future__ import annotations

from pathlib import Path

from locdex.agent.change_journal import ChangeJournal
from locdex.events import EventBus
from locdex.project import discover_project_instructions, project_instruction_prompt
from locdex.session import (
    SessionState,
    SessionTask,
    create_checkpoint,
    load_checkpoint,
    undo_checkpoint,
)
from locdex.session import state as session_state
from locdex.session import checkpoints as checkpoint_module


def test_session_state_round_trips(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(
        session_state,
        "user_cache_dir",
        lambda *args, **kwargs: str(cache),
    )

    state = SessionState.create(
        repo_path=str(tmp_path / "repo"),
        model="qwen25-7b",
        permission_mode="ask",
        sandbox_mode="workspace-write",
    )
    state.add_note("Do not modify migrations.")
    state.add_task(
        SessionTask(
            task="Fix auth.",
            status="completed",
            model="qwen25-7b",
            sandbox_mode="workspace-write",
            permission_mode="ask",
            summary="Fixed auth.",
            files_modified=["src/auth.py"],
            verification_passed=True,
            checkpoint_id="abc",
        )
    )
    state.latest_diff = "diff"
    state.save()

    loaded = SessionState.load(state.session_id)

    assert loaded.repo_path == str((tmp_path / "repo").resolve())
    assert loaded.notes == ["Do not modify migrations."]
    assert loaded.tasks[0].summary == "Fixed auth."
    assert loaded.latest_checkpoint_id == "abc"


def test_checkpoint_undo_restores_before_bytes(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(
        checkpoint_module,
        "user_cache_dir",
        lambda *args, **kwargs: str(cache),
    )

    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    journal = ChangeJournal(str(tmp_path))
    journal.capture("app.py")
    target.write_text("VALUE = 2\n", encoding="utf-8")
    journal.record_success("app.py")

    checkpoint = create_checkpoint(
        session_id="session",
        repo_path=str(tmp_path),
        journal_payload=journal.checkpoint_payload(),
        task="Change value.",
    )
    assert checkpoint is not None
    loaded = load_checkpoint("session", checkpoint.checkpoint_id)

    outcome = undo_checkpoint(loaded)

    assert outcome["ok"] is True
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_checkpoint_refuses_to_overwrite_diverged_file(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(
        checkpoint_module,
        "user_cache_dir",
        lambda *args, **kwargs: str(cache),
    )

    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    journal = ChangeJournal(str(tmp_path))
    journal.capture("app.py")
    target.write_text("VALUE = 2\n", encoding="utf-8")
    journal.record_success("app.py")

    checkpoint = create_checkpoint(
        session_id="session",
        repo_path=str(tmp_path),
        journal_payload=journal.checkpoint_payload(),
    )
    assert checkpoint is not None

    target.write_text("VALUE = user_change\n", encoding="utf-8")
    outcome = undo_checkpoint(checkpoint)

    assert outcome["ok"] is False
    assert outcome["conflicts"] == ["app.py"]
    assert target.read_text(encoding="utf-8") == "VALUE = user_change\n"


def test_project_instructions_and_skills_are_discovered(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "Use pnpm and never edit migrations.\n",
        encoding="utf-8",
    )
    locdex_dir = tmp_path / ".locdex"
    skill_dir = locdex_dir / "skills"
    skill_dir.mkdir(parents=True)
    (locdex_dir / "instructions.md").write_text(
        "Run auth tests before finishing.\n",
        encoding="utf-8",
    )
    (skill_dir / "release.md").write_text(
        "For releases, update CHANGELOG.md first.\n",
        encoding="utf-8",
    )

    discovered = discover_project_instructions(str(tmp_path))
    prompt = project_instruction_prompt(str(tmp_path))

    assert "AGENTS.md" in discovered.files
    assert ".locdex/instructions.md" in discovered.files
    assert discovered.skills[0]["name"] == "release"
    assert "Use pnpm" in prompt
    assert "LOCAL PROJECT SKILLS" in prompt


def test_event_bus_preserves_order():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda event: seen.append(event.kind))

    bus.emit("agent.started")
    bus.emit("tool.requested", tool="read_file")
    bus.emit("tool.completed", tool="read_file")

    assert seen == ["agent.started", "tool.requested", "tool.completed"]
    assert [event.kind for event in bus.history] == seen
