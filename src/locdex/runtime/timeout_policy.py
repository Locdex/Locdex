from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_cache_dir

from ..models.profiles import get_model_profile
from .hardware import HardwareProfile, detect_hardware


@dataclass(frozen=True)
class InferenceTimeoutBudget:
    load_seconds: float
    generate_seconds: float
    source: str
    backend: str
    estimated_tokens_per_second: float

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _override() -> float | None:
    """An explicit override controls both phases, without silently growing."""
    raw = os.getenv("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
        return _clamp(value, 20, 600) if math.isfinite(value) else None
    except ValueError:
        return None


def _cache_path() -> Path:
    base = Path(
        os.getenv("LOCDEX_CACHE_DIR", user_cache_dir("locdex", "Locdex"))
    ).expanduser()
    return base / "inference" / "speed-v1.json"


def _key(model_key: str, backend: str) -> str:
    # No device IDs, code, prompts, paths, network addresses, or user identities.
    return f"{model_key}:{backend}"


def _read_samples() -> dict:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def observed_speed(model_key: str, backend: str) -> float | None:
    sample = _read_samples().get(_key(model_key, backend))
    if not isinstance(sample, dict):
        return None
    try:
        speed = float(sample["tokens_per_second"])
        return speed if math.isfinite(speed) and 0.1 <= speed <= 1000 else None
    except (KeyError, ValueError, TypeError):
        return None


def record_generation_speed(
    model_key: str,
    backend: str,
    *,
    seconds: float,
    output_tokens: int,
) -> bool:
    """Maintain a local-only EMA of measured completion throughput.

    Ignore tiny samples and invalid usage. Never send this cache to telemetry.
    """
    if (
        not math.isfinite(seconds)
        or seconds <= 0
        or not isinstance(output_tokens, int)
        or isinstance(output_tokens, bool)
        or output_tokens < 16
        or output_tokens > 100000
    ):
        return False
    rate = output_tokens / seconds
    if not 0.1 <= rate <= 1000:
        return False
    data = _read_samples()
    old = observed_speed(model_key, backend)
    smooth = rate if old is None else 0.7 * old + 0.3 * rate
    row = dict(data.get(_key(model_key, backend), {}))
    row.update({
        "tokens_per_second": round(smooth, 3),
        "observations": min(10000, int(row.get("observations", 0)) + 1),
    })
    data[_key(model_key, backend)] = row
    return _save_samples(data)


def _save_samples(data: dict) -> bool:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return False
    return True


def record_inference_timeout(
    model_key: str,
    backend: str,
    *,
    phase: str,
    seconds: float,
) -> bool:
    """Raise a bounded *local-only* phase floor after a real hard timeout.

    Do not treat a timeout as a throughput observation. This prevents repeated
    first-use underestimates on a slow machine without faking tokens/sec.
    """
    if phase not in {"loading", "generating"} or not math.isfinite(seconds) or seconds <= 0:
        return False
    field = "load_timeout_floor" if phase == "loading" else "generate_timeout_floor"
    maximum = 210.0 if phase == "loading" else 360.0
    row_key = _key(model_key, backend)
    data = _read_samples()
    row = dict(data.get(row_key, {}))
    previous = row.get(field, 0)
    try:
        previous = float(previous)
    except (ValueError, TypeError):
        previous = 0
    row[field] = round(_clamp(max(previous, seconds * 1.65), 0, maximum), 1)
    data[row_key] = row
    return _save_samples(data)


def _timeout_floor(model_key: str, backend: str, phase: str) -> float:
    row = _read_samples().get(_key(model_key, backend), {})
    if not isinstance(row, dict):
        return 0.0
    value = row.get(
        "load_timeout_floor" if phase == "loading" else "generate_timeout_floor",
        0,
    )
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 <= number <= 360 else 0.0
    except (ValueError, TypeError):
        return 0.0


def estimate_inference_timeout(
    model_key: str,
    *,
    hardware: HardwareProfile | None = None,
    max_tokens: int = 512,
    prompt_tokens: int = 0,
    prefer_cloud_fallback: bool = False,
) -> InferenceTimeoutBudget:
    """Bounded estimates, not claimed performance benchmarks.

    First-use budgets are based on GGUF model size, memory pressure, CPU cores,
    and whether the selected backend can plausibly fit the model in VRAM.
    Measured per-model throughput refines future inference budgets.
    """
    hw = hardware or detect_hardware()
    profile = get_model_profile(model_key)
    size = max(0.5, profile.approximate_size_gb)
    gpu = (
        hw.backend in {"cuda", "metal"}
        and (hw.backend == "metal" or (hw.vram_free_gb or 0) >= size * 1.15)
    )
    backend = "gpu" if gpu else "cpu"
    cores = max(1, hw.physical_cpu_count or max(1, hw.cpu_count // 2))
    core_factor = _clamp((cores / 4) ** 0.35, 0.65, 1.6)
    theoretical_speed = (
        (50.0 if gpu else 17.0) * (1.12 / size) ** 0.6
        * (1.0 if gpu else core_factor)
    )
    theoretical_speed = _clamp(theoretical_speed, 0.7, 100)
    measured = observed_speed(model_key, backend)
    # Avoid a single unusually fast sample causing premature timeouts.
    speed = theoretical_speed if measured is None else min(theoretical_speed * 2.0, measured)
    low_cpu = not gpu and cores <= 2
    tight_memory = (
        hw.available_ram_gb is not None
        and hw.available_ram_gb < max(3.0, size * 1.6)
    )
    memory_pressure = (
        1.65 if tight_memory else
        1.3 if hw.available_ram_gb is not None and hw.available_ram_gb < size * 2.0
        else 1.0
    )
    # Laptop-class dual-core CPUs spend substantial time evaluating prompts
    # and initializing their first native inference call. A 35s floor yields
    # false failures even for the 1.5B smoke model; budget conservatively
    # until measured rates become available.
    load_floor = 70 if low_cpu and tight_memory else 50 if low_cpu else 35
    generation_floor = (
        115 if low_cpu and tight_memory and measured is None else
        90 if low_cpu and measured is None else 35
    )
    load = _clamp(
        max(
            load_floor,
            18 + size * (1.5 if gpu else 5.0) * memory_pressure,
            _timeout_floor(model_key, backend, "loading"),
        ),
        35, 210,
    )
    tokens = max(1, min(8192, int(max_tokens)))
    prompt = max(0, min(65536, int(prompt_tokens)))
    generate = _clamp(
        max(
            generation_floor,
            16 + ((tokens * 1.35 + prompt / 10) / speed) * memory_pressure,
            _timeout_floor(model_key, backend, "generating"),
        ),
        35, 360,
    )

    if prefer_cloud_fallback:
        # Fail over sooner once cloud use has been explicitly authorized.
        # Still leave modest CPU systems time to generate a short answer.
        load = min(load, 75)
        generate = min(generate, 110)

    override = _override()
    if override is not None:
        return InferenceTimeoutBudget(override, override, "explicit_override", backend, round(speed, 2))
    return InferenceTimeoutBudget(
        round(load, 1), round(generate, 1),
        "measured_speed" if measured is not None else "model_and_hardware_estimate",
        backend, round(speed, 2),
    )
