from __future__ import annotations

import importlib
import importlib.metadata
import sys
from dataclasses import asdict, dataclass

from .hardware import HardwareProfile, detect_hardware
from .installer import plan_runtime_install


@dataclass(frozen=True)
class RuntimeStatus:
    installed: bool
    import_ok: bool
    healthy: bool
    package_version: str | None
    python_version: str
    hardware_backend: str
    expected_backend: str
    active_backend: str | None
    gpu_offload_supported: bool | None
    wheel_index: str | None
    reason: str
    import_error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _installed_version() -> str | None:
    for distribution in ("llama-cpp-python", "llama_cpp_python"):
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _gpu_offload_supported() -> bool:
    low_level = importlib.import_module("llama_cpp.llama_cpp")
    checker = getattr(low_level, "llama_supports_gpu_offload", None)
    if checker is None:
        return False
    return bool(checker())


def runtime_status(
    hardware: HardwareProfile | None = None,
    *,
    expected_backend: str | None = None,
) -> RuntimeStatus:
    hardware = hardware or detect_hardware()
    version = _installed_version()
    try:
        plan = plan_runtime_install(hardware, backend=expected_backend or "auto")
        expected = plan.backend
        wheel_index = plan.index_url
    except Exception as exc:
        expected = expected_backend or hardware.backend or "cpu"
        wheel_index = None
        plan_error = str(exc)
    else:
        plan_error = None

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    if version is None:
        return RuntimeStatus(
            installed=False,
            import_ok=False,
            healthy=False,
            package_version=None,
            python_version=python_version,
            hardware_backend=hardware.backend,
            expected_backend=expected,
            active_backend=None,
            gpu_offload_supported=None,
            wheel_index=wheel_index,
            reason=plan_error or "llama-cpp-python is not installed for this interpreter",
        )

    try:
        importlib.import_module("llama_cpp")
        gpu = _gpu_offload_supported()
    except Exception as exc:
        return RuntimeStatus(
            installed=True,
            import_ok=False,
            healthy=False,
            package_version=version,
            python_version=python_version,
            hardware_backend=hardware.backend,
            expected_backend=expected,
            active_backend=None,
            gpu_offload_supported=None,
            wheel_index=wheel_index,
            reason="llama-cpp-python is installed but cannot be imported",
            import_error=str(exc)[:500],
        )

    if expected in {"cuda", "metal"}:
        active = expected if gpu else "cpu"
        healthy = gpu
        reason = (
            f"runtime ready with {expected} GPU offload"
            if gpu
            else f"runtime imported, but this binary does not report GPU offload support required for {expected}"
        )
    else:
        active = "cpu"
        healthy = True
        reason = "runtime ready with CPU backend"

    return RuntimeStatus(
        installed=True,
        import_ok=True,
        healthy=healthy,
        package_version=version,
        python_version=python_version,
        hardware_backend=hardware.backend,
        expected_backend=expected,
        active_backend=active,
        gpu_offload_supported=gpu,
        wheel_index=wheel_index,
        reason=reason,
    )


def verify_runtime() -> RuntimeStatus:
    return runtime_status()
