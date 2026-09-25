from __future__ import annotations

import argparse
import json
import sys

from .cloud_fallback import cloud_status
from .config import load_local_model_config, select_model, selected_model_key
from .editor import get_workspace_context
from .local_runtime import LocalRuntimeError, smoke_test_runtime
from .memory import init_db, recall_similar, save_memory
from .model_manager import (
    ModelInstallError,
    all_model_statuses,
    install_model,
    model_status,
    remove_model,
)
from .model_profiles import MODEL_PROFILES, get_model_profile
from .planner import get_metrics_report
from .router import route_task
from .runtime_manager import RuntimeInstallError, install_runtime, runtime_status
from .telemetry import (
    classify_task_locally,
    clear_local_telemetry,
    detect_workspace_language,
    flush_telemetry,
    log_routing_outcome,
    set_telemetry_enabled,
    telemetry_preview,
    telemetry_status,
)


def _format_size(size: int | None) -> str:
    if not size:
        return "unknown"
    return f"{size / (1024 ** 3):.2f} GiB"


def _print_hardware(status: dict) -> None:
    accelerator = status.get("accelerator") or "CPU"
    ram = status.get("system_ram_gb")
    ram_text = f", {ram:.1f} GiB RAM" if isinstance(ram, (int, float)) else ""
    print(f" ✓ Hardware: {accelerator} [{status.get('backend')}] {ram_text}")
    if status.get("vram_gb"):
        print(f" ✓ GPU memory: {status['vram_gb']:.1f} GiB")


def startup_diagnostic() -> None:
    print("\n[System] Running environment diagnostics...")
    rt = runtime_status()
    _print_hardware(rt)
    if rt["installed"]:
        installed_backend = rt.get("installed_backend") or "unknown"
        print(f" ✓ Locdex runtime: llama-cpp-python {rt['version']} ({installed_backend})")
    else:
        print(" ⚠ Local runtime not installed. Run `locdex setup` before local inference.")

    status = model_status()
    if status["installed"]:
        print(
            f" ✓ Model: {status['display_name']} ({_format_size(status['size_bytes'])}) "
            f"[{status['status']}]"
        )
    else:
        print(
            f" ℹ Selected model: {status['display_name']} [{status['status']}], not downloaded. "
            f"Run `locdex model install {status['model']}` or `locdex setup`."
        )
    cloud = cloud_status()
    if cloud["enabled"]:
        models = ", ".join(cloud["models"])
        print(f" ✓ Cloud fallback: {cloud['provider']} → {models}")
    elif cloud["provider"]:
        print(f" ℹ Cloud fallback provider '{cloud['provider']}' is configured but incomplete/disabled.")
    else:
        print(" ℹ Cloud fallback is disabled until a provider and model are explicitly configured.")
    print("-" * 60)


def _build_context(db_conn, user_input: str) -> dict:
    past_examples = recall_similar(db_conn, user_input)
    memory_string = "\n\n".join(past_examples) if past_examples else "None available yet."
    workspace_string = get_workspace_context(".")
    return {
        "repo_path": ".",
        "system_prompt": (
            f"RELEVANT PAST EXAMPLES:\n{memory_string}\n\n"
            f"WORKSPACE ARCHITECTURE MAP:\n{workspace_string}"
        ),
    }


def _run_task(db_conn, user_input: str) -> dict:
    print("[System] Reading workspace context...")
    context = _build_context(db_conn, user_input)
    routed = route_task(user_input, "general_task", context, {})
    source = routed.get("source", "unknown")
    result = routed.get("result", {})
    summary = str(result.get("summary", ""))

    success = result.get("status") == "completed"
    if success:
        print(f"[{source}] ✓ {summary}")
        save_memory(db_conn, user_input, summary, success=True)
    else:
        print(f"[{source}] {summary or 'Task was not completed.'}")
        save_memory(db_conn, user_input, summary or "Incomplete task", success=False)

    log_routing_outcome(
        classify_task_locally(user_input),
        detect_workspace_language(context.get("repo_path", ".")),
        source if source in {"local", "cloud", "none"} else "none",
        success=success,
        attempts=max(1, int(result.get("steps", 1) or 1)),
        local_model=selected_model_key(),
        cloud_provider=routed.get("provider"),
        cloud_model=routed.get("model"),
        escalation_reason=routed.get("escalation_reason") or "none",
    )
    return routed


def chat_loop() -> None:
    print("Welcome to Locdex Chat")
    print("Locdex works directly in the current directory like a normal coding agent.")
    print("Ask it to edit files, run tests, inspect diffs, or use Git: e.g. 'commit these changes' or 'pull latest'.")
    print("Commands: budget | model | exit")

    startup_diagnostic()
    db_conn = init_db()

    while True:
        try:
            user_input = input("\n> ").strip()
            command = user_input.lower()

            if command in {"exit", "quit"}:
                print(get_metrics_report())
                flush = flush_telemetry()
                if flush.get("sent"):
                    print(f"[Telemetry] Sent {flush['runs']} aggregated run(s) in {flush['buckets']} bucket(s).")
                break
            if command in {"budget", "stats"}:
                print(get_metrics_report())
                continue
            if command == "model":
                print(model_status())
                continue
            if not user_input:
                continue

            _run_task(db_conn, user_input)

        except KeyboardInterrupt:
            print("\nExiting Locdex...")
            print(get_metrics_report())
            flush_telemetry()
            break
        except Exception as exc:  # noqa: BLE001
            print(f"\n[Error] {exc}")


def _model_command(action: str, model_key: str | None) -> int:
    try:
        if action == "list":
            selected = selected_model_key()
            for key, profile in MODEL_PROFILES.items():
                mark = "*" if key == selected else " "
                print(
                    f"{mark} {key:5}  {profile.display_name}  ~{profile.approximate_size_gb:.1f} GB  "
                    f"[{profile.status}]"
                )
            return 0

        key = model_key or selected_model_key()
        profile = get_model_profile(key)
        config = load_local_model_config(profile.key)

        if action == "use":
            select_model(profile.key)
            print(f"Selected Locdex model: {profile.key} — {profile.display_name}")
            return 0
        if action == "install":
            path = install_model(config)
            print(f"Installed {profile.key}: {path}")
            return 0
        if action == "status":
            if model_key:
                print(model_status(config))
            else:
                for status in all_model_statuses():
                    print(status)
            return 0
        if action == "remove":
            removed = remove_model(config)
            print(f"Removed {profile.key}." if removed else f"Model {profile.key} was not installed.")
            return 0
    except (ModelInstallError, ValueError) as exc:
        print(f"Model error: {exc}", file=sys.stderr)
        return 2
    return 2


def _runtime_command(action: str) -> int:
    try:
        if action == "status":
            print(runtime_status(refresh_hardware=True))
            return 0
        if action in {"install", "repair"}:
            profile = install_runtime(force=(action == "repair"))
            print(f"Locdex runtime ready: {profile.backend} ({profile.accelerator or 'CPU'})")
            return 0
    except RuntimeInstallError as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 2
    return 2



def _telemetry_command(action: str) -> int:
    if action == "status":
        print(json.dumps(telemetry_status(), indent=2, sort_keys=True))
        return 0
    if action == "enable":
        set_telemetry_enabled(True)
        status = telemetry_status()
        print("Telemetry enabled. Locdex will record only aggregate routing outcomes.")
        if not status["endpoint_configured"]:
            print("No telemetry endpoint is configured, so nothing will leave this machine yet.")
        return 0
    if action == "disable":
        set_telemetry_enabled(False)
        print("Telemetry disabled. Existing local aggregate data is retained until you clear it.")
        return 0
    if action == "preview":
        print(json.dumps(telemetry_preview(), indent=2, sort_keys=True))
        return 0
    if action == "flush":
        print(json.dumps(flush_telemetry(), indent=2, sort_keys=True))
        return 0
    if action == "clear":
        clear_local_telemetry()
        print("Local telemetry aggregates cleared.")
        return 0
    return 2

def _choose_setup_model(requested: str | None) -> str:
    if requested:
        return get_model_profile(requested).key
    if sys.stdin.isatty():
        print("\nChoose a local model:")
        print("  1) qwen  — Qwen3-Coder 30B-A3B Q4_K_M (~18.6 GB), supported/default")
        print("  2) kimi  — Kimi-K3 distilled 9B Q4_K_M (~5.8 GB), experimental")
        choice = input("Model [1/qwen]: ").strip().lower()
        if choice in {"2", "kimi"}:
            return "kimi"
    return "qwen"


def _setup(model_key: str | None, skip_model: bool, skip_smoke: bool) -> int:
    try:
        print("[Locdex setup] Detecting hardware and installing a prebuilt runtime...")
        hardware = install_runtime()
        _print_hardware(runtime_status())
        print(f" ✓ Runtime backend: {hardware.backend}")

        key = _choose_setup_model(model_key)
        profile = get_model_profile(key)
        select_model(key)
        ram = hardware.system_ram_gb
        if ram is not None and ram < profile.minimum_ram_gb:
            print(
                f" ⚠ {profile.display_name} normally needs at least ~{profile.minimum_ram_gb} GiB RAM. "
                f"Detected {ram:.1f} GiB. Consider `locdex setup --model kimi`."
            )
        elif ram is not None and ram < profile.recommended_ram_gb:
            print(
                f" ℹ {profile.display_name} is more comfortable around {profile.recommended_ram_gb} GiB RAM; "
                f"detected {ram:.1f} GiB."
            )

        if not skip_model:
            install_model(load_local_model_config(key))

        if not skip_smoke and not skip_model:
            print("[Locdex setup] Running local inference smoke test...")
            result = smoke_test_runtime(load_local_model_config(key))
            print(f" ✓ Smoke test passed using {result['model']} on {result['backend']}")
        else:
            print(" ℹ Smoke test skipped.")

        print(f"\nLocdex setup complete. Selected model: {key} ({profile.status}).")
        print("Run `locdex chat` inside a repository to begin testing.")
        return 0
    except (RuntimeInstallError, ModelInstallError, LocalRuntimeError, ValueError) as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2


def cli() -> None:
    parser = argparse.ArgumentParser(description="Locdex - local-first AI coding agent")
    parser.add_argument("--task", dest="root_task", help="Run one agent task and exit (legacy convenience)")
    sub = parser.add_subparsers(dest="command")

    chat = sub.add_parser("chat", help="Start Locdex in the current workspace")
    chat.add_argument("--task", help="Run one agent task and exit")

    setup = sub.add_parser("setup", help="Detect hardware, install runtime, choose/download a model, and smoke-test")
    setup.add_argument("--model", choices=sorted(MODEL_PROFILES), help="Local model to select")
    setup.add_argument("--skip-model", action="store_true", help="Install runtime but do not download a model")
    setup.add_argument("--skip-smoke", action="store_true", help="Skip the inference smoke test")

    model = sub.add_parser("model", help="Manage local models")
    model.add_argument("action", choices=["list", "install", "status", "remove", "use"])
    model.add_argument("model_key", nargs="?", choices=sorted(MODEL_PROFILES))

    runtime = sub.add_parser("runtime", help="Inspect or install the detected local inference runtime")
    runtime.add_argument("action", choices=["status", "install", "repair"])

    telemetry = sub.add_parser("telemetry", help="Inspect or control privacy-minimized routing telemetry")
    telemetry.add_argument("action", choices=["status", "enable", "disable", "preview", "flush", "clear"])

    args = parser.parse_args()
    command = args.command or "chat"

    if command == "setup":
        raise SystemExit(_setup(args.model, args.skip_model, args.skip_smoke))
    if command == "model":
        raise SystemExit(_model_command(args.action, args.model_key))
    if command == "runtime":
        raise SystemExit(_runtime_command(args.action))
    if command == "telemetry":
        raise SystemExit(_telemetry_command(args.action))

    task = getattr(args, "task", None) or getattr(args, "root_task", None)
    if task:
        db_conn = init_db()
        routed = _run_task(db_conn, task)
        flush_telemetry()
        if routed.get("result", {}).get("status") != "completed":
            raise SystemExit(1)
        return

    chat_loop()


if __name__ == "__main__":
    cli()
