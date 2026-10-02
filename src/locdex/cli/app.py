from __future__ import annotations

import argparse
import json

from .. import __version__
from ..agent import AgentEngine
from ..models import MODEL_PROFILES
from ..routing import LearnedRouter, RoutingPolicy, RoutingSession, local_candidates, profile_task
from ..routing.updater import status as router_status, update_from_manifest
from ..runtime import detect_hardware
from ..telemetry import clear as telemetry_clear
from ..telemetry import enabled as telemetry_enabled
from ..telemetry import mode as telemetry_mode
from ..telemetry import endpoint as telemetry_endpoint
from ..telemetry import flush as telemetry_flush
from ..telemetry import peek as telemetry_peek
from ..telemetry import set_enabled as telemetry_set_enabled
from ..telemetry import set_mode as telemetry_set_mode
from ..telemetry import set_endpoint as telemetry_set_endpoint


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="locdex", description="Local-first coding-agent runtime")
    p.add_argument("--version", action="version", version=f"locdex {__version__}")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("status")
    sub.add_parser("models")
    prep = sub.add_parser("prepare")
    prep.add_argument("--task", required=True); prep.add_argument("--repo", default="."); prep.add_argument("--cloud", action="store_true"); prep.add_argument("--mode", choices=["local_only","balanced","fast","quality"], default="balanced")
    route = sub.add_parser("route")
    route.add_argument("--task", required=True); route.add_argument("--repo", default="."); route.add_argument("--mode", choices=["local_only","balanced","fast","quality"], default="balanced")
    tel=sub.add_parser("telemetry"); tel.add_argument("action",choices=["status","enable","research","disable","preview","flush","clear","endpoint"]); tel.add_argument("value",nargs="?")
    router=sub.add_parser("router"); router.add_argument("action",choices=["status","update"]); router.add_argument("--manifest-url")
    return p


def _routing_payload(decision) -> dict:
    return {"model":decision.model,"route":decision.route,"predicted_success":decision.predicted_success,"predicted_cost":decision.predicted_cost,"reason":decision.reason,"fallback":decision.fallback,"router_version":decision.router_version,"predictions":decision.predictions}


def cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        print(json.dumps(detect_hardware().__dict__, indent=2)); return 0
    if args.command == "models":
        for key, profile in MODEL_PROFILES.items(): print(f"{key}: {profile.display_name} [{profile.status}] ~{profile.approximate_size_gb} GB")
        return 0
    if args.command == "prepare":
        result = AgentEngine().prepare(args.task,args.repo,cloud_enabled=args.cloud,routing_mode=args.mode)
        print(json.dumps({"execution_route":result["plan"].route,"context_policy":result["plan"].context_policy,"context_tokens":result["context"].total_tokens,"redactions":result["context"].redactions,"task_profile":result["task_profile"].to_features(),"router":_routing_payload(result["routing_decision"]),"items":[i.label for i in result["context"].items]},indent=2)); return 0
    if args.command == "route":
        hw=detect_hardware(); profile=profile_task(args.task,args.repo); decision=LearnedRouter().route(task=profile,models=local_candidates(hw),policy=RoutingPolicy(mode=args.mode,allow_cloud=False),session=RoutingSession())
        print(json.dumps({"task_profile":profile.to_features(),"decision":_routing_payload(decision)},indent=2)); return 0
    if args.command == "router":
        if args.action == "status": print(json.dumps(router_status(),indent=2)); return 0
        if args.action == "update": print(json.dumps(update_from_manifest(args.manifest_url),indent=2)); return 0
    if args.command == "telemetry":
        if args.action == "status": print(json.dumps({"enabled":telemetry_enabled(),"mode":telemetry_mode(),"endpoint":telemetry_endpoint() or None,"queued":len(telemetry_peek(100))},indent=2)); return 0
        if args.action == "enable": telemetry_set_mode("basic"); print("Shared routing telemetry enabled in BASIC mode: sanitized outcome metadata only."); return 0
        if args.action == "research": telemetry_set_mode("research"); print("RESEARCH consent enabled. No shadow-model evaluation is performed unless a separate research feature explicitly requests it."); return 0
        if args.action == "disable": telemetry_set_mode("off"); print("Shared routing telemetry disabled."); return 0
        if args.action == "preview": print(json.dumps(telemetry_peek(100),indent=2)); return 0
        if args.action == "flush": print(json.dumps(telemetry_flush(),indent=2)); return 0
        if args.action == "clear": telemetry_clear(); print("Telemetry queue cleared."); return 0
        if args.action == "endpoint":
            if args.value is None: print(telemetry_endpoint() or "<not configured>")
            else: telemetry_set_endpoint(args.value); print("Telemetry endpoint saved.")
            return 0
    build_parser().print_help(); return 0
