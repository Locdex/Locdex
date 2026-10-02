from __future__ import annotations

import argparse
import json

from .. import __version__
from ..agent import AgentEngine
from ..models import MODEL_PROFILES
from ..routing import LearnedRouter, RoutingPolicy, RoutingSession, local_candidates, profile_task
from ..routing.updater import status as router_status, update_from_manifest
from ..runtime import detect_hardware, install_runtime, runtime_status, verify_runtime
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
    sub.add_parser("models", help="List built-in local model profiles.")

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


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "status":
        _print_json(detect_hardware().to_dict())
        return 0

    if args.command == "models":
        for key, profile in MODEL_PROFILES.items():
            print(f"{key}: {profile.display_name} [{profile.status}] ~{profile.approximate_size_gb} GB")
        return 0

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
