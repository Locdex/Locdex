from locdex.cli.app import build_parser


def test_cli_status():
    args = build_parser().parse_args(["status"])
    assert args.command == "status"


def test_cli_prepare():
    args = build_parser().parse_args(["prepare", "--task", "inspect"])
    assert args.command == "prepare"
    assert args.task == "inspect"


def test_cli_runtime_status():
    args = build_parser().parse_args(["runtime", "status"])
    assert args.command == "runtime"
    assert args.runtime_action == "status"


def test_cli_runtime_install_backend():
    args = build_parser().parse_args(["runtime", "install", "--backend", "cuda"])
    assert args.runtime_action == "install"
    assert args.backend == "cuda"


def test_cli_model_list():
    args = build_parser().parse_args(["model", "list"])
    assert args.command == "model"
    assert args.model_action == "list"


def test_cli_model_use_smoke():
    args = build_parser().parse_args(["model", "use", "smoke"])
    assert args.model_action == "use"
    assert args.key == "smoke"


def test_cli_runtime_uninstall():
    args = build_parser().parse_args(["runtime", "uninstall"])
    assert args.command == "runtime"
    assert args.runtime_action == "uninstall"


def test_cli_run_prompt():
    args = build_parser().parse_args(["run", "--prompt", "hello", "--model", "smoke"])
    assert args.command == "run"
    assert args.prompt == "hello"
    assert args.model == "smoke"


def test_cli_task_command():
    args = build_parser().parse_args(
        ["task", "--task", "change x", "--repo", ".", "--model", "smoke", "--max-steps", "4"]
    )
    assert args.command == "task"
    assert args.task == "change x"
    assert args.model == "smoke"
    assert args.max_steps == 4


def test_cli_agents_validate():
    args = build_parser().parse_args(
        ["agents", "validate", "--config", "agents.yaml"]
    )
    assert args.command == "agents"
    assert args.agents_action == "validate"
    assert args.config == "agents.yaml"


def test_cli_agents_run_parallel():
    args = build_parser().parse_args(
        [
            "agents",
            "run",
            "--config",
            "agents.yaml",
            "--repo",
            ".",
            "--parallel",
            "3",
        ]
    )
    assert args.agents_action == "run"
    assert args.parallel == 3


def test_cli_model_qualify():
    args = build_parser().parse_args(
        [
            "model",
            "qualify",
            "qwen25-7b",
            "--max-steps",
            "10",
            "--prompt-only",
        ]
    )
    assert args.command == "model"
    assert args.model_action == "qualify"
    assert args.key == "qwen25-7b"
    assert args.max_steps == 10
    assert args.prompt_only is True


def test_cli_task_defaults_to_ask_permissions():
    args = build_parser().parse_args(
        ["task", "--task", "Inspect and fix app.py"]
    )
    assert args.permission_mode == "ask"


def test_cli_task_accepts_permission_modes():
    for mode in ("plan", "ask", "auto-edit", "trusted", "unrestricted"):
        args = build_parser().parse_args(
            [
                "task",
                "--task",
                "Inspect app.py",
                "--permission-mode",
                mode,
            ]
        )
        assert args.permission_mode == mode


def test_cli_task_defaults_to_workspace_write_sandbox():
    args = build_parser().parse_args(
        ["task", "--task", "Inspect app.py"]
    )
    assert args.sandbox == "workspace-write"


def test_cli_task_accepts_sandbox_modes():
    for mode in ("read-only", "workspace-write", "workspace-network", "unrestricted"):
        args = build_parser().parse_args(
            [
                "task",
                "--task",
                "Inspect app.py",
                "--sandbox",
                mode,
            ]
        )
        assert args.sandbox == mode


def test_cli_sandbox_status():
    args = build_parser().parse_args(["sandbox", "status"])
    assert args.command == "sandbox"
    assert args.sandbox_action == "status"


def test_cli_resume_session():
    args = build_parser().parse_args(
        ["resume", "abc123", "--repo", "."]
    )
    assert args.command == "resume"
    assert args.session_id == "abc123"


def test_cli_steer_and_cancel():
    steer = build_parser().parse_args(
        ["steer", "abc123", "Do not touch migrations."]
    )
    assert steer.command == "steer"
    assert steer.session_id == "abc123"
    assert steer.message == "Do not touch migrations."

    cancel = build_parser().parse_args(["cancel", "abc123"])
    assert cancel.command == "cancel"
    assert cancel.session_id == "abc123"
