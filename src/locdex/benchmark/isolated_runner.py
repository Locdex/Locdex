"""Docker-isolated, local-only LocdexBench trial runner.

The agent sees only a disposable fixture and an explicitly mounted GGUF file.
The grader runs in a *separate* container after the agent exits and is never
mounted into the agent process. Cloud/hybrid modes are not implemented here.

The Docker engine and pinned image are explicitly required. There is no
fallback to executing model-produced code directly on the host.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from ..models.profiles import MODEL_PROFILES, get_model_profile
from .controls import validate_agent_changes
from .manifest import ManifestError, load_manifest, verify_pinned_fixture


IMAGE_DIGEST = re.compile(r"^(?:[a-z0-9][a-z0-9./_-]*@)?sha256:[a-f0-9]{64}$")
VOLUME_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
RECORD_KEYS = {
    "schema", "task_id", "base_commit", "model", "mode", "model_sha256",
    "container_image", "status", "verified", "visible_passed", "hidden_passed",
    "wall_seconds", "max_steps", "memory_gb",
}
STATUSES = {"passed", "agent_failed", "grader_failed", "timed_out", "protected_edit", "infra_failed"}


class BenchmarkRunError(RuntimeError):
    """Docker or runner precondition failed without executing user code on the host."""


def validate_image(image: str) -> None:
    if not isinstance(image, str) or not IMAGE_DIGEST.fullmatch(image):
        raise BenchmarkRunError("Docker image must be pinned by full sha256 digest or local image ID.")


def docker_arguments(
    *,
    image: str,
    container_name: str,
    workspace: Path,
    command: list[str],
    hidden_grader: Path | None = None,
    model_path: Path | None = None,
    model_volume: str | None = None,
    model_key: str | None = None,
    readonly_workspace: bool = False,
    memory_gb: int = 8,
) -> list[str]:
    """Generate a locked-down Docker invocation without invoking it."""
    validate_image(image)
    if type(memory_gb) is not int or not 4 <= memory_gb <= 32:
        raise BenchmarkRunError("Container memory_gb must be an integer from 4 to 32.")
    # Docker --mount uses commas as field separators. Refuse paths that could
    # reinterpret a bind source as additional mount options.
    mount_paths = [workspace, hidden_grader, model_path]
    if any("," in str(path) for path in mount_paths if path is not None):
        raise BenchmarkRunError("Commas in Docker bind-mount paths are not supported.")
    mounts = [
        "--mount", f"type=bind,source={workspace},target=/workspace,readonly={'true' if readonly_workspace else 'false'}",
    ]
    if model_path is not None and model_volume is not None:
        raise BenchmarkRunError("Model bind mounts and Docker model volumes are mutually exclusive.")
    if hidden_grader is not None:
        if not readonly_workspace:
            raise BenchmarkRunError("A grader can only be mounted in a read-only grading workspace.")
        mounts += ["--mount", f"type=bind,source={hidden_grader},target=/tmp/test_hidden.py,readonly=true"]
    if model_path is not None:
        if hidden_grader is not None or readonly_workspace:
            raise BenchmarkRunError("A model file must never be mounted in the grading container.")
        mounts += ["--mount", f"type=bind,source={model_path},target=/models/model.gguf,readonly=true"]
    if model_volume is not None:
        if hidden_grader is not None or readonly_workspace:
            raise BenchmarkRunError("A model volume must never be mounted in the grading container.")
        if not VOLUME_NAME.fullmatch(model_volume):
            raise BenchmarkRunError("Invalid Docker model volume name.")
        mounts += ["--mount", f"type=volume,source={model_volume},target=/models,readonly"]
    env = [
        "-e", "HOME=/tmp", "-e", "XDG_CACHE_HOME=/tmp/.cache",
        "-e", "LOCDEX_CACHE_DIR=/tmp/locdex-cache",
        "-e", "LOCDEX_CONFIG_DIR=/tmp/locdex-config",
        "-e", "LOCDEX_TELEMETRY_MODE=off",
        "-e", "LOCDEX_CLOUD_ENABLED=0",
    ]
    if model_key is not None:
        env += ["-e", f"LOCDEX_MODEL={model_key}", "-e", "LOCDEX_MODEL_PATH=/models/model.gguf",
                "-e", "LOCDEX_BENCH_PROGRESS=1"]
        raw_context = os.getenv("LOCDEX_BENCH_CONTEXT_TOKENS", "").strip()
        if raw_context:
            try:
                context = int(raw_context)
                profile_max = get_model_profile(model_key).preferred_context
                if not (2048 <= context <= profile_max and context % 256 == 0):
                    raise ValueError
            except ValueError as exc:
                raise BenchmarkRunError(
                    "LOCDEX_BENCH_CONTEXT_TOKENS must be a multiple of 256 between 2048 and the model preferred context."
                ) from exc
            env += ["-e", f"LOCDEX_LLAMA_CONTEXT_TOKENS={context}"]
        override = os.getenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "").strip()
        if override:
            try:
                seconds = float(override)
                if not (20 <= seconds <= 600) or not seconds.is_integer():
                    raise ValueError
            except ValueError as exc:
                raise BenchmarkRunError("Inference timeout override must be an integer 20-600 seconds.") from exc
            env += ["-e", f"LOCDEX_INFERENCE_TIMEOUT_SECONDS={int(seconds)}"]
    if hidden_grader is not None:
        env += ["-e", "PYTHONPATH=/workspace"]
    return [
        "docker", "run", "--rm", "--name", container_name,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "128",
        "--memory", f"{memory_gb}g", "--cpus", "2",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
        "--workdir", "/workspace", "--user", "65534:65534",
        *mounts, *env, image, *command,
    ]


def _call_docker(argv: list[str], name: str, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, errors="replace",
            check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise
    finally:
        # A timed-out docker CLI must not leave a model still running.
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True, check=False, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            pass



def _prepare_model_volume(
    *, image: str, model_path: Path, digest: str,
    requested_volume: str | None = None,
) -> tuple[str, str]:
    """Stage once on the Linux filesystem, then verify SHA-256 before each trial.

    User-supplied volumes must already exist and are never modified. An
    automatically managed, checksum-keyed cache persists between trials.
    """
    validate_image(image)
    volume = requested_volume or f"locdexbench-gguf-{digest[:24]}"
    if not VOLUME_NAME.fullmatch(volume):
        raise BenchmarkRunError("Invalid Docker model volume name.")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise BenchmarkRunError("Invalid model checksum.")

    try:
        inspect = subprocess.run(
            ["docker", "volume", "inspect", volume],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkRunError("Could not inspect Docker model volume.") from exc

    exists = inspect.returncode == 0
    if requested_volume and not exists:
        raise BenchmarkRunError("Requested pre-staged model volume does not exist.")

    created = False
    try:
        if not exists:
            result = subprocess.run(
                ["docker", "volume", "create", volume],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if result.returncode != 0:
                raise BenchmarkRunError("Could not create Docker model cache volume.")
            created = True
            print("[LocdexBench] Copying GGUF into Docker-native storage (one-time setup)...", flush=True)
            stage_name = "locdexbench-model-stage-" + uuid.uuid4().hex[:12]
            stage_script = (
                "import os, shutil; "
                "shutil.copyfile('/source.gguf', '/stage/model.gguf.tmp'); "
                "os.replace('/stage/model.gguf.tmp', '/stage/model.gguf')"
            )
            # Staging is an infrastructure operation, not agent code execution.
            stage_args = [
                "docker", "run", "--rm", "--name", stage_name,
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "64",
                "--memory", "2g", "--cpus", "2",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
                "--user", "0:0",
                "--mount", f"type=bind,source={model_path},target=/source.gguf,readonly",
                "--mount", f"type=volume,source={volume},target=/stage",
                image, "python", "-c", stage_script,
            ]
            try:
                copied = _call_docker(stage_args, stage_name, 900)
            except subprocess.TimeoutExpired as exc:
                raise BenchmarkRunError("Timed out staging GGUF into Docker volume.") from exc
            if copied.returncode:
                raise BenchmarkRunError("Could not stage GGUF into Docker volume.")

        print("[LocdexBench] Verifying SHA-256 of Docker-native GGUF...", flush=True)
        check_name = "locdexbench-model-verify-" + uuid.uuid4().hex[:12]
        checksum_script = (
            "import hashlib; h=hashlib.sha256(); "
            "f=open('/models/model.gguf','rb'); "
            "[(h.update(chunk)) for chunk in iter(lambda: f.read(4*1024*1024), b'')]; "
            "print(h.hexdigest())"
        )
        check_args = [
            "docker", "run", "--rm", "--name", check_name,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "64",
            "--memory", "2g", "--cpus", "2",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
            "--user", "65534:65534",
            "--mount", f"type=volume,source={volume},target=/models,readonly",
            image, "python", "-c", checksum_script,
        ]
        try:
            checked = _call_docker(check_args, check_name, 180)
        except subprocess.TimeoutExpired as exc:
            raise BenchmarkRunError("Timed out verifying Docker model volume.") from exc
        if checked.returncode or checked.stdout.strip() != digest:
            raise BenchmarkRunError(
                "Docker model volume checksum mismatch or verification failure. "
                "Refusing to run an unverified model."
            )
        print("[LocdexBench] Verified Docker-native model cache.", flush=True)
        return volume, "staged" if created else "reused"
    except BaseException:
        # Only remove a volume created by this invocation on setup failure.
        # Never delete a user-provided or previously cached volume.
        if created:
            try:
                subprocess.run(
                    ["docker", "volume", "rm", volume],
                    capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        raise


def _run_agent_with_progress(argv: list[str], name: str, timeout: int):
    """Show safe heartbeats while capturing model output privately."""
    started = time.monotonic()
    print(f"[LocdexBench] Agent starting; timeout {timeout}s.", flush=True)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = None
        offset = 0
        last_event = None
        event_count = 0
        phase = "unobserved"

        def show_events():
            nonlocal offset, last_event, event_count, phase
            err.flush()
            err.seek(offset)
            raw = err.read(65536)
            offset = err.tell()
            for line in raw.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith(("[Agent]", "[Inference]")):
                    # Events originate from the agent runtime, not model responses.
                    # Keep a bounded, privacy-minimized console message.
                    safe = line[:240]
                    print(f"[LocdexBench] {safe}", flush=True)
                    last_event = safe
                    event_count += 1
                    if "CLI task started" in safe:
                        phase = "agent_startup"
                    elif "Preparing protected workspace" in safe:
                        phase = "workspace_setup"
                    elif "Planning repository retrieval" in safe:
                        phase = "retrieval_planning"
                    elif "Retrieval planning complete" in safe:
                        phase = "retrieval_ready"
                    elif "Preparing repository context" in safe:
                        phase = "context_preparation"
                    elif safe.startswith("[Inference] Loading "):
                        phase = "model_loading"
                    elif "Model ready" in safe:
                        phase = "model_ready"
                    elif "generating decision" in safe:
                        phase = "decision_generation"
                    elif "decision ready" in safe:
                        phase = "decision_ready"
                    elif safe.startswith("[Agent] Step "):
                        phase = "action_selection"
                    elif safe.startswith("[Agent] "):
                        phase = "tool_execution"

        timed_out = False
        try:
            proc = subprocess.Popen(argv, stdout=out, stderr=err)
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    proc.wait(timeout=min(15, remaining))
                    show_events()
                    break
                except subprocess.TimeoutExpired:
                    show_events()
                    print(f"[LocdexBench] Agent execution: {int(time.monotonic()-started)}s / {timeout}s; still running.", flush=True)
            if timed_out:
                show_events()
                print(f"[LocdexBench] Agent execution timed out; last observed phase: {phase}.", flush=True)
            elif event_count == 0:
                print("[LocdexBench] No agent phase events received; cause not yet identified.", flush=True)
            return (124 if timed_out else proc.returncode), {
                "stage": "agent_execution",
                "timed_out": timed_out,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "exit_code": None if timed_out else proc.returncode,
                "last_event": last_event,
                "progress_events": event_count,
                "phase": phase,
                "stderr_bytes": os.fstat(err.fileno()).st_size,
            }
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False, timeout=15)
            except (OSError, subprocess.SubprocessError):
                pass

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_trial_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict) or set(record) != RECORD_KEYS:
        raise ValueError("Trial record contains missing or unexpected fields.")
    if record["schema"] != "locdexbench-local-v0" or record["mode"] != "local-only":
        raise ValueError("Unsupported benchmark record schema or mode.")
    if record["status"] not in STATUSES or type(record["verified"]) is not bool:
        raise ValueError("Invalid trial status or success flag.")
    if record["verified"] != (record["status"] == "passed"):
        raise ValueError("Success flag conflicts with trial status.")
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,79}", record["task_id"]):
        raise ValueError("Invalid task identifier.")
    if record["model"] not in MODEL_PROFILES:
        raise ValueError("Unknown local model profile.")
    for value in (record["base_commit"], record["model_sha256"]):
        if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{40}|[a-f0-9]{64}", value):
            raise ValueError("Invalid content digest.")
    validate_image(record["container_image"])
    for key in ("visible_passed", "hidden_passed"):
        if record[key] is not None and type(record[key]) is not bool:
            raise ValueError("Invalid verification outcome.")
    if type(record["max_steps"]) is not int or not 1 <= record["max_steps"] <= 32:
        raise ValueError("Invalid step budget.")
    if type(record["memory_gb"]) is not int or not 4 <= record["memory_gb"] <= 32:
        raise ValueError("Invalid container memory cap.")
    if type(record["wall_seconds"]) not in (float, int) or not 0 <= record["wall_seconds"] <= 100000:
        raise ValueError("Invalid elapsed time.")


def run_local_trial(
    *,
    manifest_path: str | Path,
    repo_root: str | Path,
    image: str,
    model_key: str,
    model_path: str | Path,
    model_volume: str | None = None,
    output_path: str | Path | None = None,
    memory_gb: int = 8,
) -> dict[str, Any]:
    """Run a pinned task in a network-disabled container with separate grading.

    Image must already be present locally and contain Locdex, llama-cpp-python,
    Python unittest, and a supported GGUF backend. No Docker image is pulled.
    """
    task = load_manifest(manifest_path)
    root = Path(repo_root).resolve()
    verify_pinned_fixture(task, root)
    validate_image(image)
    if type(memory_gb) is not int or not 4 <= memory_gb <= 32:
        raise BenchmarkRunError("Container memory_gb must be an integer from 4 to 32.")
    if model_key not in MODEL_PROFILES:
        raise BenchmarkRunError("Unknown local model profile.")
    untrusted_model = Path(model_path).expanduser()
    if untrusted_model.is_symlink():
        raise BenchmarkRunError("Model symlinks are not accepted.")
    model = untrusted_model.resolve()
    if not model.is_file() or model.suffix.lower() != ".gguf":
        raise BenchmarkRunError("Local GGUF file is missing or unsafe.")
    try:
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, check=False, timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkRunError("Docker image inspection failed.") from exc
    if inspect.returncode:
        raise BenchmarkRunError("Pinned Docker image is not available locally.")
    digest = _sha256(model)
    volume, cache_state = _prepare_model_volume(
        image=image, model_path=model, digest=digest,
        requested_volume=model_volume,
    )
    start = time.monotonic()
    visible_passed: bool | None = None
    hidden_passed: bool | None = None
    status = "infra_failed"
    diagnostics: dict[str, Any] = {"stage": "setup", "timed_out": False}
    with tempfile.TemporaryDirectory(prefix="locdexbench-trial-") as temp:
        parent = Path(temp)
        before = parent / "original"
        workspace = parent / "workspace"
        shutil.copytree(root / task.fixture, before)
        shutil.copytree(root / task.fixture, workspace)
        os.chmod(workspace, 0o777)
        os.chmod(workspace / "core.py", 0o666)
        # The disposable Git repository is initialized by the same confined
        # non-root Docker user as the agent, avoiding host ownership issues.
        init_name = "locdexbench-init-" + uuid.uuid4().hex[:12]
        init_args = docker_arguments(
            image=image, container_name=init_name, workspace=workspace,
            command=["git", "init", "--quiet", "/workspace"],
        )
        if _call_docker(init_args, init_name, 30).returncode:
            raise BenchmarkRunError("Cannot initialize the isolated fixture Git repository.")
        grader = (root / task.hidden_grader).resolve()
        agent_name = "locdexbench-agent-" + uuid.uuid4().hex[:12]
        argv = docker_arguments(
            image=image, container_name=agent_name, workspace=workspace,
            model_volume=volume, model_key=model_key, memory_gb=memory_gb,
            command=[
                "locdex", "task", "--repo", "/workspace",
                "--task", task.task, "--model", model_key,
                "--max-steps", str(task.limits["model_steps"]),
                "--mode", "local_only", "--sandbox", "workspace-write",
                "--permission-mode", "trusted", "--json",
            ],
        )
        try:
            returncode, diagnostics = _run_agent_with_progress(argv, agent_name, int(task.limits["wall_seconds"]))
            if diagnostics["timed_out"]:
                status = "timed_out"
            elif returncode:
                status = "agent_failed"
            else:
                try:
                    validate_agent_changes(task, before, workspace)
                except ManifestError:
                    status = "protected_edit"
                else:
                    def grade(command: list[str], with_hidden: bool) -> bool:
                        name = "locdexbench-grade-" + uuid.uuid4().hex[:12]
                        params = docker_arguments(
                            image=image, container_name=name, workspace=workspace,
                            hidden_grader=grader if with_hidden else None,
                            readonly_workspace=True, command=command,
                        )
                        return _call_docker(params, name, 45).returncode == 0

                    print("[LocdexBench] Agent finished; running independent grading.", flush=True)
                    diagnostics["stage"] = "visible_grading"
                    visible_passed = grade([
                        "python", "-m", "unittest", "discover", "-s",
                        "tests", "-p", "test_visible.py",
                    ], False)
                    diagnostics["stage"] = "hidden_grading"
                    hidden_passed = grade([
                        "python", "-m", "unittest", "discover", "-s",
                        "/tmp", "-p", "test_hidden.py",
                    ], True)
                    status = "passed" if visible_passed and hidden_passed else "grader_failed"
                    diagnostics["stage"] = "completed"
        except subprocess.TimeoutExpired:
            status = "timed_out"
            diagnostics["timed_out"] = True
        except (OSError, subprocess.SubprocessError):
            status = "infra_failed"
            diagnostics["stage"] = "infrastructure"

    diagnostics["model_storage"] = "docker_volume"
    diagnostics["model_cache"] = cache_state
    result = {
        "schema": "locdexbench-local-v0",
        "task_id": task.id, "base_commit": task.base_commit,
        "model": model_key, "mode": "local-only",
        "model_sha256": digest, "container_image": image,
        "status": status, "verified": status == "passed",
        "visible_passed": visible_passed, "hidden_passed": hidden_passed,
        "wall_seconds": round(time.monotonic() - start, 3),
        "max_steps": task.limits["model_steps"], "memory_gb": memory_gb,
    }
    validate_trial_record(result)
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        diag_path = destination.with_name(destination.stem + ".diagnostics.json")
        diag_path.write_text(
            json.dumps({"task_id": task.id, "status": status, **diagnostics}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[LocdexBench] Diagnostic metadata: {diag_path}", flush=True)
    return result
