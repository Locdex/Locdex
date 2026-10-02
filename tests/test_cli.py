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
