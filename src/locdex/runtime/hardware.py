from __future__ import annotations

import csv
import ctypes
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

_GIB = 1024 ** 3
_RELATION_PROCESSOR_CORE = 0


@dataclass(frozen=True)
class HardwareProfile:
    # Keep the first six fields stable for backward compatibility with v3.2 callers.
    system: str
    machine: str
    cpu_count: int
    total_ram_gb: float | None
    available_ram_gb: float | None
    backend: str
    cpu_name: str | None = None
    physical_cpu_count: int | None = None
    accelerator: str | None = None
    gpu_name: str | None = None
    vram_total_gb: float | None = None
    vram_free_gb: float | None = None
    cuda_version: str | None = None
    driver_version: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _round_gb(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _run_text(args: list[str], timeout: float = 5.0) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=flags,
        )
    except (subprocess.TimeoutExpired, OSError):
        # Hardware probes are advisory. A slow or unavailable external utility
        # must never make Locdex status/agent preparation fail.
        return ""

    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _linux_ram() -> tuple[float | None, float | None]:
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0])
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        return (
            _round_gb(total * 1024 / _GIB) if total else None,
            _round_gb(available * 1024 / _GIB) if available else None,
        )
    except (OSError, ValueError):
        return None, None


def _windows_memory() -> tuple[float | None, float | None]:
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None
        return _round_gb(status.ullTotalPhys / _GIB), _round_gb(status.ullAvailPhys / _GIB)
    except (AttributeError, OSError, ValueError):
        return None, None


def _mac_memory() -> tuple[float | None, float | None]:
    raw = _run_text(["sysctl", "-n", "hw.memsize"])
    try:
        total = _round_gb(int(raw) / _GIB) if raw else None
    except ValueError:
        total = None
    return total, None


def _windows_cpu_name() -> str | None:
    fallback = os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor() or None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        name = str(value).strip()
        return name or fallback
    except (ImportError, OSError, ValueError):
        return fallback


def _windows_physical_cpu_count() -> int | None:
    """
    Count processor-core relationship records with the native Windows API.

    This avoids WMI/CIM/PowerShell, which can be slow or unavailable on
    developer machines and should not sit on Locdex's hot path.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        length = ctypes.c_ulong(0)

        # First call obtains the required variable-length buffer size.
        kernel32.GetLogicalProcessorInformationEx(
            _RELATION_PROCESSOR_CORE,
            None,
            ctypes.byref(length),
        )
        if not length.value:
            return None

        buffer = ctypes.create_string_buffer(length.value)
        if not kernel32.GetLogicalProcessorInformationEx(
            _RELATION_PROCESSOR_CORE,
            buffer,
            ctypes.byref(length),
        ):
            return None

        raw = buffer.raw[: length.value]
        offset = 0
        count = 0
        while offset + 8 <= len(raw):
            relationship = int.from_bytes(raw[offset : offset + 4], "little", signed=True)
            size = int.from_bytes(raw[offset + 4 : offset + 8], "little")
            if size < 8 or offset + size > len(raw):
                break
            if relationship == _RELATION_PROCESSOR_CORE:
                count += 1
            offset += size
        return count or None
    except (AttributeError, OSError, ValueError):
        return None


def _windows_cpu() -> tuple[str | None, int | None, int | None]:
    return _windows_cpu_name(), _windows_physical_cpu_count(), os.cpu_count() or None


def _nvidia_smi_path() -> str | None:
    found = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if found:
        return found
    if platform.system() == "Windows":
        candidates = [
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "nvidia-smi.exe",
            Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return None


def _to_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def _parse_nvidia_query(raw: str) -> list[dict]:
    rows: list[dict] = []
    for row in csv.reader(line for line in raw.splitlines() if line.strip()):
        if len(row) < 4:
            continue
        total_mib = _to_float(row[1])
        free_mib = _to_float(row[2])
        rows.append(
            {
                "name": row[0].strip(),
                "vram_total_gb": _round_gb(total_mib / 1024) if total_mib is not None else None,
                "vram_free_gb": _round_gb(free_mib / 1024) if free_mib is not None else None,
                "driver_version": row[3].strip() or None,
            }
        )
    return rows


def _detect_nvidia() -> dict | None:
    executable = _nvidia_smi_path()
    if not executable:
        return None

    query = _run_text(
        [
            executable,
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=5.0,
    )
    rows = _parse_nvidia_query(query)
    if not rows:
        return None

    gpu = max(rows, key=lambda row: row.get("vram_total_gb") or 0.0)
    banner = _run_text([executable], timeout=5.0)
    match = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)?)", banner, re.IGNORECASE)
    gpu["cuda_version"] = match.group(1) if match else None
    return gpu


def detect_hardware() -> HardwareProfile:
    system = platform.system()
    machine = platform.machine()
    logical = os.cpu_count() or 1
    physical: int | None = None
    cpu_name = platform.processor() or None
    total_ram: float | None = None
    available_ram: float | None = None

    if system == "Windows":
        total_ram, available_ram = _windows_memory()
        win_name, win_physical, win_logical = _windows_cpu()
        cpu_name = win_name or cpu_name
        physical = win_physical
        logical = win_logical or logical
    elif system == "Linux":
        total_ram, available_ram = _linux_ram()
    elif system == "Darwin":
        total_ram, available_ram = _mac_memory()

    accelerator: str | None = None
    gpu_name: str | None = None
    vram_total: float | None = None
    vram_free: float | None = None
    cuda_version: str | None = None
    driver_version: str | None = None
    backend = "cpu"

    nvidia = _detect_nvidia()
    if nvidia:
        accelerator = "nvidia"
        gpu_name = nvidia.get("name")
        vram_total = nvidia.get("vram_total_gb")
        vram_free = nvidia.get("vram_free_gb")
        cuda_version = nvidia.get("cuda_version")
        driver_version = nvidia.get("driver_version")
        backend = "cuda"
    elif system == "Darwin" and machine.lower() in {"arm64", "aarch64"}:
        accelerator = "apple"
        gpu_name = "Apple Silicon"
        backend = "metal"

    return HardwareProfile(
        system=system,
        machine=machine,
        cpu_count=logical,
        total_ram_gb=total_ram,
        available_ram_gb=available_ram,
        backend=backend,
        cpu_name=cpu_name,
        physical_cpu_count=physical,
        accelerator=accelerator,
        gpu_name=gpu_name,
        vram_total_gb=vram_total,
        vram_free_gb=vram_free,
        cuda_version=cuda_version,
        driver_version=driver_version,
    )
