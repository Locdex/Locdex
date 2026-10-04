from __future__ import annotations

import argparse
import json

from .. import __version__
from .interactive import run_interactive
from ..agent import AgentEngine
from ..multiagent import AgentSpecError, MultiAgentError, WorktreeError, load_agent_spec, run_agents
from ..models import (
    MODEL_PROFILES,
    ModelInstallError,
    all_model_statuses,
    install_model,
    model_status,
    remove_model,
    select_model,
    selected_model_key,
)
from ..qualification import qualify_model
from ..security import (
    ApprovalChoice,
    PermissionController,
    PermissionMode,
    PermissionRequest,
)
from ..routing import LearnedRouter, RoutingPolicy, RoutingSession, local_candidates, profile_task
from ..routing.updater import status as router_status, update_from_manifest
from ..runtime import (
    RuntimeExecutionError,
    detect_hardware,
    install_runtime,
    run_prompt,
    runtime_status,
    uninstall_runtime,
    verify_runtime,
)
from ..telemetry import clear as telemetry_clear
from ..telemetry import enabled as telemetry_enabled
from ..telemetry import endpoint as telemetry_endpoint
from ..telemetry import flush as telemetry_flush
from ..telemetry import mode as telemetry_mode
from ..telemetry import peek as telemetry_peek
from ..telemetry import set_endpoint as telemetry_set_endpoint
from ..telemetry import set_mode as telemetry_set_mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="locdex", description="Local-first coding-agent runtime")
    parser.add_argument("--version", action="version", version=f"locdex {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show detected hardware.")
    sub.add_parser("models", help="Compatibility alias for model list.")
    resume_cmd = sub.add_parser("resume", help="Resume an interactive Locdex session.")
    resume_cmd.add_argument("session_id", nargs="?")
    resume_cmd.add_argument("--repo", default=".")

    model = sub.add_parser("model", help="Manage local GGUF models.")
    model_sub = model.add_subparsers(dest="model_action", required=True)
    model_sub.add_parser("list", help="List built-in model profiles and install state.")
    status_cmd = model_sub.add_parser("status", help="Show selected model or one named model.")
    status_cmd.add_argument("key", nargs="?")
    use_cmd = model_sub.add_parser("use", help="Persist the selected local model.")
    use_cmd.add_argument("key", choices=sorted(MODEL_PROFILES))
    install_cmd = model_sub.add_parser("install", help="Download and verify a model explicitly.")
    install_cmd.add_argument("key", choices=sorted(MODEL_PROFILES))
    install_cmd.add_argument("--force", action="store_true")
    remove_cmd = model_sub.add_parser("remove", help="Remove a Locdex-managed model from cache.")
    remove_cmd.add_argument("key", choices=sorted(MODEL_PROFILES))
    qualify_cmd = model_sub.add_parser(
        "qualify",
        help="Run a reproducible local prompt + coding-agent qualification probe.",
    )
    qualify_cmd.add_argument("key", choices=sorted(MODEL_PROFILES))
    qualify_cmd.add_argument("--max-steps", type=int, default=8)
    qualify_cmd.add_argument("--force-hardware", action="store_true")
    qualify_cmd.add_argument("--prompt-only", action="store_true")

    prep = sub.add_parser("prepare")
    prep.add_argument("--task", required=True)
    prep.add_argument("--repo", default=".")
    prep.add_argument("--cloud", action="store_true")
    prep.add_argument("--mode", choices=["local_only", "balanced", "fast", "quality"], default="balanced")

    route = sub.add_parser("route")
    route.add_argument("--task", required=True)
    route.add_argument("--repo", default=".")
    route.add_argument("--mode", choices=["local_only", "balanced", "fast", "quality"], default="balanced")

    runtime = sub.add_parser("runtime", help="Inspect, install, repair, or uninstall the llama.cpp runtime.")
    runtime_sub = runtime.add_subparsers(dest="runtime_action", required=True)
    runtime_sub.add_parser("status", help="Show installed runtime and backend health.")
    runtime_sub.add_parser("verify", help="Verify the installed runtime can load the expected backend.")
    for action in ("install", "repair"):
        command = runtime_sub.add_parser(action)
        command.add_argument("--backend", choices=["auto", "cuda", "cpu", "metal"], default="auto")
    runtime_sub.add_parser("uninstall", help="Remove llama-cpp-python but keep downloaded models.")

    run_cmd = sub.add_parser("run", help="Run one prompt on the selected installed local model.")
    run_cmd.add_argument("--prompt", required=True)
    run_cmd.add_argument("--model", choices=sorted(MODEL_PROFILES))
    run_cmd.add_argument("--system")
    run_cmd.add_argument("--max-tokens", type=int, default=256)
    run_cmd.add_argument("--temperature", type=float, default=0.1)
    run_cmd.add_argument("--json", action="store_true", dest="json_output")

    task_cmd = sub.add_parser("task", help="Execute a bounded coding-agent task in a repository.")
    task_cmd.add_argument("--task", required=True)
    task_cmd.add_argument("--repo", default=".")
    task_cmd.add_argument("--model", choices=sorted(MODEL_PROFILES))
    task_cmd.add_argument("--max-steps", type=int, default=6)
    task_cmd.add_argument(
        "--mode",
        choices=["local_only", "balanced", "fast", "quality"],
        default="balanced",
    )
    task_cmd.add_argument(
        "--permission-mode",
        choices=[mode.value for mode in PermissionMode],
        default=PermissionMode.ASK.value,
        help=(
            "Tool approval policy: plan, ask (default), auto-edit, trusted, "
            "or unrestricted."
        ),
    )
    task_cmd.add_argument("--json", action="store_true", dest="json_output")

    agents_cmd = sub.add_parser("agents", help="Run user-defined agents in isolated Git worktrees.")
    agents_sub = agents_cmd.add_subparsers(dest="agents_action", required=True)
    agents_validate = agents_sub.add_parser("validate", help="Validate an agent YAML config.")
    agents_validate.add_argument("--config", required=True)
    agents_run = agents_sub.add_parser("run", help="Run agents from a YAML config.")
    agents_run.add_argument("--config", required=True)
    agents_run.add_argument("--repo", default=".")
    agents_run.add_argument("--parallel", type=int, default=1)
    agents_run.add_argument("--json", action="store_true", dest="json_output")

    telemetry = sub.add_parser("telemetry")
    telemetry.add_argument(
        "action",
        choices=["status", "enable", "research", "disable", "preview", "flush", "clear", "endpoint"],
    )
    telemetry.add_argument("value", nargs="?")

    router = sub.add_parser("router")
    router.add_argument("action", choices=["status", "update"])
    router.add_argument("--manifest-url")
    return parser


def _routing_payload(decision) -> dict:
    return {
        "model": decision.model,
        "route": decision.route,
        "predicted_success": decision.predicted_success,
        "predicted_cost": decision.predicted_cost,
        "reason": decision.reason,
        "fallback": decision.fallback,
        "router_version": decision.router_version,
        "predictions": decision.predictions,
    }


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2))


def _print_model_rows() -> None:
    for row in all_model_statuses():
        marker = "*" if row["selected"] else " "
        installed = "installed" if row["installed"] else "not installed"
        print(
            f"{marker} {row['model']}: {row['display_name']} "
            f"[{row['profile_status']}, {installed}, {row['hardware_tier']}] "
            f"~{row['approximate_size_gb']} GB | RAM {row['minimum_ram_gb']}+ "
            f"(recommended {row['recommended_ram_gb']} GB)"
        )


def _interactive_permission(request: PermissionRequest) -> ApprovalChoice:
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


def _permission_controller(
    mode: str,
    *,
    interactive: bool,
) -> PermissionController:
    callback = _interactive_permission if interactive and mode == PermissionMode.ASK.value else None
    return PermissionController(mode, approval_callback=callback)


def cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command is None:
        return run_interactive(".")

    if args.command == "resume":
        return run_interactive(args.repo, resume_id=args.session_id)

    if args.command == "status":
        _print_json(detect_hardware().to_dict())
        return 0

    if args.command == "models":
        _print_model_rows()
        return 0

    if args.command == "model":
        try:
            if args.model_action == "list":
                _print_model_rows()
                return 0
            if args.model_action == "status":
                _print_json(model_status(args.key or selected_model_key()))
                return 0
            if args.model_action == "use":
                key = select_model(args.key)
                _print_json(model_status(key))
                return 0
            if args.model_action == "install":
                _print_json(install_model(args.key, force=args.force))
                return 0
            if args.model_action == "remove":
                removed = remove_model(args.key)
                _print_json({"model": args.key, "removed": removed})
                return 0
            if args.model_action == "qualify":
                result = qualify_model(
                    args.key,
                    max_steps=args.max_steps,
                    force_hardware=args.force_hardware,
                    agent_task=not args.prompt_only,
                )
                _print_json(result)
                return 0 if result.get("passed") else 1
        except (ModelInstallError, ValueError) as exc:
            print(f"Locdex model error: {exc}")
            return 1

    if args.command == "runtime":
        if args.runtime_action == "status":
            _print_json(runtime_status().to_dict())
            return 0
        if args.runtime_action == "verify":
            status = verify_runtime()
            _print_json(status.to_dict())
            return 0 if status.healthy else 1
        if args.runtime_action in {"install", "repair"}:
            try:
                result = install_runtime(
                    backend=args.backend,
                    repair=args.runtime_action == "repair",
                )
            except RuntimeError as exc:
                print(f"Locdex runtime error: {exc}")
                return 1
            _print_json(result)
            return 0
        if args.runtime_action == "uninstall":
            try:
                _print_json(uninstall_runtime())
            except RuntimeError as exc:
                print(f"Locdex runtime error: {exc}")
                return 1
            return 0

    if args.command == "run":
        try:
            result = run_prompt(
                args.prompt,
                model_key=args.model,
                system=args.system,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
        except RuntimeExecutionError as exc:
            print(f"Locdex inference error: {exc}")
            return 1

        if args.json_output:
            _print_json(result)
        else:
            print(result["text"])
        return 0

    if args.command == "task":
        if args.json_output and args.permission_mode == PermissionMode.ASK.value:
            print(
                "Locdex permission error: --json cannot use interactive 'ask' mode. "
                "Choose --permission-mode plan, auto-edit, trusted, or unrestricted."
            )
            return 1

        permission_controller = _permission_controller(
            args.permission_mode,
            interactive=not args.json_output,
        )
        engine = AgentEngine(model_key=args.model)
        try:
            result = engine.execute(
                args.task,
                args.repo,
                max_steps=args.max_steps,
                routing_mode=args.mode,
                progress=None if args.json_output else print,
                permission_controller=permission_controller,
            )
        except RuntimeExecutionError as exc:
            print(f"Locdex agent error: {exc}")
            return 1

        if args.json_output:
            _print_json(result)
        else:
            print()
            print(result["summary"])
            modified = result.get("files_modified") or []
            if modified:
                print("Modified: " + ", ".join(modified))

            rolled_back = result.get("rolled_back_files") or []
            if rolled_back:
                print("Rolled back incomplete changes: " + ", ".join(rolled_back))

            verification = result.get("verification") or {}
            checks = verification.get("checks") or []
            if checks:
                check_text = ", ".join(
                    f"{check.get('name')}={check.get('status')}"
                    for check in checks
                )
                print(f"Verification: {check_text}")

            preexisting = result.get("preexisting_changes") or []
            if preexisting:
                print("Pre-existing changes preserved: " + ", ".join(preexisting))

            print(
                f"Status: {result['status']} | model: {result['model']} | "
                f"steps: {result['steps']} | verification attempts: "
                f"{result.get('verification_attempts', 0)}"
            )
        return 0 if result["status"] == "completed" else 1

    if args.command == "agents":
        try:
            spec = load_agent_spec(args.config)
            if args.agents_action == "validate":
                _print_json(spec.to_dict())
                return 0

            if args.agents_action == "run":
                result = run_agents(
                    spec,
                    args.repo,
                    parallel=args.parallel,
                    progress=None if args.json_output else print,
                    approval_callback=None if args.json_output else _interactive_permission,
                )
                if args.json_output:
                    _print_json(result)
                else:
                    print()
                    print(
                        f"Multi-agent run {result['run_id']}: "
                        f"{result['agents_completed']}/{result['agents_total']} completed"
                    )
                    for row in result["agents"]:
                        agent_result = row["result"]
                        workspace = row["workspace"]
                        print(
                            f"- {row['name']}: {agent_result.get('status')} | "
                            f"model={row['model']} | branch={workspace['branch']}"
                        )
                        print(f"  workspace: {workspace['path']}")
                    print("No agent changes were auto-committed or auto-merged.")
                return 0 if result["agents_completed"] == result["agents_total"] else 1
        except (AgentSpecError, MultiAgentError, WorktreeError, ValueError) as exc:
            print(f"Locdex multi-agent error: {exc}")
            return 1

    if args.command == "prepare":
        result = AgentEngine().prepare(
            args.task,
            args.repo,
            cloud_enabled=args.cloud,
            routing_mode=args.mode,
        )
        _print_json(
            {
                "execution_route": result["plan"].route,
                "context_policy": result["plan"].context_policy,
                "context_tokens": result["context"].total_tokens,
                "redactions": result["context"].redactions,
                "selected_model": result["selected_model"],
                "task_profile": result["task_profile"].to_features(),
                "router": _routing_payload(result["routing_decision"]),
                "items": [item.label for item in result["context"].items],
            }
        )
        return 0

    if args.command == "route":
        hardware = detect_hardware()
        profile = profile_task(args.task, args.repo)
        decision = LearnedRouter().route(
            task=profile,
            models=local_candidates(hardware),
            policy=RoutingPolicy(mode=args.mode, allow_cloud=False),
            session=RoutingSession(),
        )
        _print_json({"task_profile": profile.to_features(), "decision": _routing_payload(decision)})
        return 0

    if args.command == "router":
        if args.action == "status":
            _print_json(router_status())
            return 0
        if args.action == "update":
            _print_json(update_from_manifest(args.manifest_url))
            return 0

    if args.command == "telemetry":
        if args.action == "status":
            _print_json(
                {
                    "enabled": telemetry_enabled(),
                    "mode": telemetry_mode(),
                    "endpoint": telemetry_endpoint() or None,
                    "queued": len(telemetry_peek(100)),
                }
            )
            return 0
        if args.action == "enable":
            telemetry_set_mode("basic")
            print("Shared routing telemetry enabled in BASIC mode: sanitized outcome metadata only.")
            return 0
        if args.action == "research":
            telemetry_set_mode("research")
            print(
                "RESEARCH consent enabled. No shadow-model evaluation is performed unless a separate "
                "research feature explicitly requests it."
            )
            return 0
        if args.action == "disable":
            telemetry_set_mode("off")
            print("Shared routing telemetry disabled.")
            return 0
        if args.action == "preview":
            print(json.dumps(telemetry_peek(100), indent=2))
            return 0
        if args.action == "flush":
            _print_json(telemetry_flush())
            return 0
        if args.action == "clear":
            telemetry_clear()
            print("Telemetry queue cleared.")
            return 0
        if args.action == "endpoint":
            if args.value is None:
                print(telemetry_endpoint() or "<not configured>")
            else:
                telemetry_set_endpoint(args.value)
                print("Telemetry endpoint saved.")
            return 0

    build_parser().print_help()
    return 0
