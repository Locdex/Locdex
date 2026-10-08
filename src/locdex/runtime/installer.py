from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict, dataclass

from .hardware import HardwareProfile, detect_hardware

WHEEL_INDEX_ROOT = "https://abetlen.github.io/llama-cpp-python/whl"
SUPPORTED_PREBUILT_PYTHON = {(3, 10), (3, 11), (3, 12)}
CUDA_TRACKS = (
    ((11, 8), "cu118"),
    ((12, 1), "cu121"),
    ((12, 2), "cu122"),
    ((12, 3), "cu123"),
    ((12, 4), "cu124"),
    ((12, 5), "cu125"),
    ((13, 0), "cu130"),
    ((13, 2), "cu132"),
)


@dataclass(frozen=True)
class RuntimeInstallPlan:
    backend: str
    index_url: str
    cuda_track: str | None
    python_version: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _python_version_tuple() -> tuple[int, int]:
    return sys.version_info.major, sys.version_info.minor


def _parse_version(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        parts = value.strip().split(".")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return None


def select_cuda_track(cuda_version: str | None) -> str | None:
    target = _parse_version(cuda_version)
    if target is None:
        return None
    eligible = [(version, track) for version, track in CUDA_TRACKS if version <= target]
    return eligible[-1][1] if eligible else None


def plan_runtime_install(
    hardware: HardwareProfile | None = None,
    *,
    backend: str = "auto",
) -> RuntimeInstallPlan:
    hardware = hardware or detect_hardware()
    requested = backend.strip().lower()
    if requested not in {"auto", "cpu", "cuda", "metal"}:
        raise ValueError("backend must be one of: auto, cpu, cuda, metal")

    py = _python_version_tuple()
    if py not in SUPPORTED_PREBUILT_PYTHON:
        raise RuntimeError(
            f"Locdex prebuilt llama.cpp runtime currently supports Python 3.10-3.12; "
            f"this interpreter is {sys.version_info.major}.{sys.version_info.minor}."
        )

    selected = hardware.backend if requested == "auto" else requested
    reason = f"selected {selected} from hardware backend {hardware.backend}"

    if selected == "cuda":
        if hardware.accelerator != "nvidia" and requested != "auto":
            raise RuntimeError("CUDA runtime requested but no NVIDIA accelerator was detected.")
        track = select_cuda_track(hardware.cuda_version)
        if track:
            return RuntimeInstallPlan(
                backend="cuda",
                index_url=f"{WHEEL_INDEX_ROOT}/{track}",
                cuda_track=track,
                python_version=f"{py[0]}.{py[1]}",
                reason=f"NVIDIA detected; using newest official wheel track not newer than CUDA {hardware.cuda_version}",
            )
        if requested != "auto":
            raise RuntimeError(
                f"No supported official prebuilt CUDA wheel track matches detected CUDA "
                f"{hardware.cuda_version or 'unknown'}."
            )
        selected = "cpu"
        reason = "NVIDIA detected but no supported official CUDA wheel track was resolvable; explicit CPU fallback"

    if selected == "metal":
        if not (hardware.system == "Darwin" and hardware.machine.lower() in {"arm64", "aarch64"}):
            if requested != "auto":
                raise RuntimeError("Metal runtime requested on non-Apple-Silicon hardware.")
            selected = "cpu"
            reason = "Metal was not available on this host; explicit CPU fallback"
        else:
            return RuntimeInstallPlan(
                backend="metal",
                index_url=f"{WHEEL_INDEX_ROOT}/metal",
                cuda_track=None,
                python_version=f"{py[0]}.{py[1]}",
                reason="Apple Silicon detected; using official Metal wheel index",
            )

    return RuntimeInstallPlan(
        backend="cpu",
        index_url=f"{WHEEL_INDEX_ROOT}/cpu",
        cuda_track=None,
        python_version=f"{py[0]}.{py[1]}",
        reason=reason if selected == "cpu" else "using official CPU wheel index",
    )


def build_install_command(plan: RuntimeInstallPlan, *, force_reinstall: bool = False) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--prefer-binary",
        "--only-binary=llama-cpp-python",
    ]
    if force_reinstall:
        command.append("--force-reinstall")
    command.extend(["--progress-bar", "on", "llama-cpp-python", "--extra-index-url", plan.index_url])
    return command


def build_uninstall_command() -> list[str]:
    return [sys.executable, "-m", "pip", "uninstall", "-y", "llama-cpp-python"]


def install_runtime(*, backend: str = "auto", repair: bool = False) -> dict:
    from .manager import runtime_status

    hardware = detect_hardware()
    plan = plan_runtime_install(hardware, backend=backend)
    before = runtime_status(hardware)
    if not repair and before.healthy and before.active_backend == plan.backend:
        return {
            "changed": False,
            "reason": "runtime already healthy for selected backend",
            "plan": plan.to_dict(),
            "status": before.to_dict(),
        }

    command = build_install_command(plan, force_reinstall=repair)
    print(
        f"Installing llama.cpp runtime ({plan.backend}); pip will display "
        "real download percentages when package sizes are available.",
        flush=True,
    )
    print("1/2  Downloading and installing prebuilt runtime wheels...", flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Prebuilt llama-cpp-python installation failed with exit code {result.returncode}. "
            "Locdex did not attempt a source build."
        )

    print("2/2  Verifying installed backend...", flush=True)
    after = runtime_status(hardware, expected_backend=plan.backend)
    if not after.healthy:
        raise RuntimeError(
            "llama-cpp-python installed but runtime verification failed: " + after.reason
        )
    print("✓ Locdex runtime installed and verified.", flush=True)
    return {
        "changed": True,
        "plan": plan.to_dict(),
        "command": command,
        "status": after.to_dict(),
    }


def uninstall_runtime() -> dict:
    from .manager import runtime_status

    before = runtime_status()
    if not before.installed:
        return {
            "changed": False,
            "reason": "llama-cpp-python is not installed for this interpreter",
            "status": before.to_dict(),
        }

    command = build_uninstall_command()
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"llama-cpp-python uninstall failed with exit code {result.returncode}."
        )

    return {
        "changed": True,
        "command": command,
        "reason": "llama-cpp-python removed; installed GGUF models were left intact",
    }
