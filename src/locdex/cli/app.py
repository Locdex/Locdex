from __future__ import annotations

import argparse
import json

from .. import __version__
from ..agent import AgentEngine
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

    prep = sub.add_parser("prepare")
    prep.add_argument("--task", required=True)
    prep.add_argument("--repo", default=".")
    prep.add_argument("--cloud", action="store_true")
    prep.add_argument("--mode", choices=["local_only", "balanced", "fast", "quality"], default="balanced")

    route = sub.add_parser("route")
    route.add_argument("--task", required=True)
    route.add_argument("--repo", default=".")
    route.add_argument("--mode", choices=["local_only", "balanced", "fast", "quality"], default="balanced")

    runtime = sub.add_parser("runtime", help="Inspect, install, or repair the llama.cpp runtime.")
    runtime_sub = runtime.add_subparsers(dest="runtime_action", required=True)
    runtime_sub.add_parser("status", help="Show installed runtime and backend health.")
    runtime_sub.add_parser("verify", help="Verify the installed runtime can load the expected backend.")
    for action in ("install", "repair"):
        command = runtime_sub.add_parser(action)
        command.add_argument("--backend", choices=["auto", "cuda", "cpu", "metal"], default="auto")

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
            f"[{row['profile_status']}, {installed}] ~{row['approximate_size_gb']} GB"
        )


def cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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
