from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import locdex_cache_dir

RUNTIME_VERSION = "0.3.35"
RUNTIME_REQUIREMENT = f"llama-cpp-python>={RUNTIME_VERSION},<0.4"
WHEEL_BASE = "https://abetlen.github.io/llama-cpp-python/whl"
GITHUB_RELEASE_BASE = "https://github.com/abetlen/llama-cpp-python/releases/download"
SUPPORTED_CUDA_WHEELS = ("13.2", "13.0", "12.5", "12.4", "12.3", "12.2", "12.1", "11.8")


class RuntimeInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwareProfile:
    system: str
    machine: str
    python: str
    backend: str
    accelerator: str | None
    vram_gb: float | None
    system_ram_gb: float | None
    cuda_version: str | None
    wheel_index: str
    auto_gpu_layers: int

    @property
    def fingerprint(self) -> str:
        values = [
            self.system,
            self.machine,
            self.python,
            self.backend,
            self.accelerator or "",
            self.cuda_version or "",
        ]
        return "|".join(values)


def _run_capture(argv: list[str], timeout: int = 4) -> str | None:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr or "").strip()


def _system_ram_gb() -> float | None:
    try:
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round((pages * page_size) / (1024**3), 1)
    except (ValueError, OSError, AttributeError):
        pass

    if platform.system() == "Windows":
        output = _run_capture(["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"])
        if output:
            match = re.search(r"TotalPhysicalMemory=(\d+)", output)
            if match:
                return round(int(match.group(1)) / (1024**3), 1)
    if platform.system() == "Darwin":
        output = _run_capture(["sysctl", "-n", "hw.memsize"])
        if output and output.isdigit():
            return round(int(output) / (1024**3), 1)
    return None


def _nvidia_profile() -> tuple[str, float | None, str | None] | None:
    if not shutil.which("nvidia-smi"):
        return None
    query = _run_capture(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if not query:
        return None
    first = query.splitlines()[0]
    parts = [part.strip() for part in first.split(",")]
    name = parts[0] if parts else "NVIDIA GPU"
    vram = None
    if len(parts) > 1:
        try:
            vram = round(float(parts[1]) / 1024, 1)
        except ValueError:
            pass

    general = _run_capture(["nvidia-smi"])
    cuda = None
    if general:
        match = re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)", general)
        if match:
            cuda = match.group(1)
    return name, vram, cuda


def _nearest_cuda_wheel(cuda_version: str | None) -> str | None:
    if not cuda_version:
        return None
    try:
        detected = tuple(int(x) for x in cuda_version.split(".")[:2])
    except ValueError:
        return None
    supported = [tuple(int(x) for x in version.split(".")) for version in SUPPORTED_CUDA_WHEELS]
    eligible = [version for version in supported if version <= detected]
    if not eligible:
        return None
    chosen = max(eligible)
    return f"cu{chosen[0]}{chosen[1]}"


def detect_hardware() -> HardwareProfile:
    system = platform.system()
    machine = platform.machine().lower()
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    ram = _system_ram_gb()

    nvidia = _nvidia_profile()
    if nvidia:
        name, vram, cuda = nvidia
        cuda_wheel = _nearest_cuda_wheel(cuda)
        if cuda_wheel and sys.version_info[:2] in {(3, 10), (3, 11), (3, 12)}:
            return HardwareProfile(
                system=system,
                machine=machine,
                python=py,
                backend="cuda",
                accelerator=name,
                vram_gb=vram,
                system_ram_gb=ram,
                cuda_version=cuda,
                wheel_index=f"{WHEEL_BASE}/{cuda_wheel}",
                auto_gpu_layers=-1,
            )

    if (
        system == "Darwin"
        and machine in {"arm64", "aarch64"}
        and sys.version_info[:2] in {(3, 10), (3, 11), (3, 12)}
    ):
        return HardwareProfile(
            system=system,
            machine=machine,
            python=py,
            backend="metal",
            accelerator="Apple Silicon",
            vram_gb=None,
            system_ram_gb=ram,
            cuda_version=None,
            wheel_index=f"{WHEEL_BASE}/metal",
            auto_gpu_layers=-1,
        )

    if system == "Linux" and (shutil.which("rocminfo") or shutil.which("rocm-smi")):
        name = (
            _run_capture(["rocm-smi", "--showproductname"], timeout=3)
            if shutil.which("rocm-smi")
            else None
        )
        return HardwareProfile(
            system=system,
            machine=machine,
            python=py,
            backend="rocm",
            accelerator=(name.splitlines()[-1].strip() if name else "AMD ROCm GPU"),
            vram_gb=None,
            system_ram_gb=ram,
            cuda_version=None,
            wheel_index=f"{WHEEL_BASE}/rocm72",
            auto_gpu_layers=-1,
        )

    if system == "Windows" and os.environ.get("LOCDEX_AMD_HIP") == "1":
        return HardwareProfile(
            system=system,
            machine=machine,
            python=py,
            backend="hip-radeon",
            accelerator="AMD Radeon",
            vram_gb=None,
            system_ram_gb=ram,
            cuda_version=None,
            wheel_index=f"{WHEEL_BASE}/hip-radeon",
            auto_gpu_layers=-1,
        )

    if system in {"Linux", "Windows"} and shutil.which("vulkaninfo"):
        return HardwareProfile(
            system=system,
            machine=machine,
            python=py,
            backend="vulkan",
            accelerator="Vulkan-capable GPU",
            vram_gb=None,
            system_ram_gb=ram,
            cuda_version=None,
            wheel_index=f"{WHEEL_BASE}/vulkan",
            auto_gpu_layers=-1,
        )

    return HardwareProfile(
        system=system,
        machine=machine,
        python=py,
        backend="cpu",
        accelerator=None,
        vram_gb=None,
        system_ram_gb=ram,
        cuda_version=None,
        wheel_index=f"{WHEEL_BASE}/cpu",
        auto_gpu_layers=0,
    )


def _cache_path() -> Path:
    return locdex_cache_dir() / "runtime-profile.json"


def cache_hardware_profile(profile: HardwareProfile) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    payload["fingerprint"] = profile.fingerprint
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_cached_hardware_profile() -> dict | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def effective_hardware_profile(refresh: bool = False) -> HardwareProfile:
    detected = detect_hardware()
    cached = None if refresh else load_cached_hardware_profile()
    if not cached or cached.get("fingerprint") != detected.fingerprint:
        cache_hardware_profile(detected)
    return detected


def _install_marker_path() -> Path:
    return locdex_cache_dir() / "runtime-install.json"


def _read_install_marker() -> dict | None:
    path = _install_marker_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_install_marker(profile: HardwareProfile, *, source: str = "locdex") -> None:
    path = _install_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "backend": profile.backend,
                "fingerprint": profile.fingerprint,
                "wheel_index": profile.wheel_index,
                "version": installed_runtime_version(),
                "source": source,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def installed_runtime_version() -> str | None:
    try:
        return importlib.metadata.version("llama-cpp-python")
    except importlib.metadata.PackageNotFoundError:
        return None


def _infer_installed_backend(profile: HardwareProfile, marker: dict) -> str | None:
    marked = marker.get("backend")
    if isinstance(marked, str) and marked:
        return marked

    # A manually installed runtime can only be safely inferred as CPU when
    # hardware detection itself found no accelerated backend. On accelerated
    # machines, a markerless wheel could be CPU or GPU-enabled, so report
    # "unknown" rather than claiming the wrong backend.
    if installed_runtime_version() is not None and profile.backend == "cpu":
        return "cpu"
    if installed_runtime_version() is not None:
        return "unknown"
    return None


def runtime_status(refresh_hardware: bool = False) -> dict:
    profile = effective_hardware_profile(refresh=refresh_hardware)
    marker = _read_install_marker() or {}
    version = installed_runtime_version()
    return {
        "installed": version is not None,
        "version": version,
        "installed_backend": _infer_installed_backend(profile, marker),
        "backend": profile.backend,
        "accelerator": profile.accelerator,
        "vram_gb": profile.vram_gb,
        "system_ram_gb": profile.system_ram_gb,
        "python": profile.python,
        "wheel_index": profile.wheel_index,
        "auto_gpu_layers": profile.auto_gpu_layers,
    }


def _index_install_command(profile: HardwareProfile) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--only-binary=:all:",
        "--timeout",
        "120",
        "--retries",
        "4",
        RUNTIME_REQUIREMENT,
        "--extra-index-url",
        profile.wheel_index,
    ]


def _direct_release_wheel_url(profile: HardwareProfile) -> str | None:
    # Verified official fallback for the generic CPU Windows AMD64 wheel.
    # Other backends keep using their official wheel indexes until their
    # direct-release asset matrix is tested on those platforms.
    if profile.backend == "cpu" and profile.system == "Windows" and profile.machine in {"amd64", "x86_64"}:
        filename = f"llama_cpp_python-{RUNTIME_VERSION}-py3-none-win_amd64.whl"
        return f"{GITHUB_RELEASE_BASE}/v{RUNTIME_VERSION}/{filename}"
    return None


def _direct_install_command(url: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--only-binary=:all:",
        "--timeout",
        "120",
        "--retries",
        "4",
        url,
    ]


def install_runtime(force: bool = False) -> HardwareProfile:
    profile = effective_hardware_profile(refresh=True)
    marker = _read_install_marker() or {}
    version = installed_runtime_version()

    if version and not force:
        if marker.get("backend") == profile.backend and marker.get("fingerprint") == profile.fingerprint:
            return profile

        # Adopt a markerless manual CPU install on a CPU-only machine. This
        # covers a direct official wheel install without forcing a re-download.
        if not marker and profile.backend == "cpu":
            cache_hardware_profile(profile)
            _write_install_marker(profile, source="adopted-manual-install")
            return profile

    primary = subprocess.run(_index_install_command(profile), check=False)
    install_source = "official-wheel-index"

    if primary.returncode != 0:
        fallback_url = _direct_release_wheel_url(profile)
        if not fallback_url:
            raise RuntimeInstallError(
                "Could not install a compatible prebuilt Locdex runtime from the official wheel index, "
                "and no verified direct-release fallback is available for "
                f"{profile.system}/{profile.machine}, Python {profile.python}, backend {profile.backend}. "
                "Locdex did not attempt a source build."
            )

        fallback = subprocess.run(_direct_install_command(fallback_url), check=False)
        if fallback.returncode != 0:
            raise RuntimeInstallError(
                "Could not install the prebuilt Locdex runtime from either the official wheel index "
                "or the verified GitHub release fallback. Locdex did not attempt a source build. "
                "Check network access to github.com and retry `locdex runtime install`."
            )
        install_source = "official-github-release"

    if installed_runtime_version() is None:
        raise RuntimeInstallError("Runtime installer completed but llama-cpp-python is still unavailable.")

    cache_hardware_profile(profile)
    _write_install_marker(profile, source=install_source)
    return profile
