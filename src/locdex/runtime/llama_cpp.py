from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..models import get_model_profile, installed_model_path, selected_model_key
from .hardware import HardwareProfile, detect_hardware
from .manager import runtime_status


class RuntimeExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class InferencePlan:
    model_key: str
    model_path: str
    backend: str
    n_ctx: int
    n_threads: int
    n_gpu_layers: int
    max_tokens: int
    temperature: float

    def to_dict(self) -> dict:
        return asdict(self)


def _threads_for(hardware: HardwareProfile) -> int:
    if hardware.physical_cpu_count:
        return max(1, hardware.physical_cpu_count)
    return max(1, hardware.cpu_count - 1)


def plan_inference(
    *,
    model_key: str | None = None,
    hardware: HardwareProfile | None = None,
    max_tokens: int = 256,
    temperature: float = 0.1,
) -> InferencePlan:
    key = model_key or selected_model_key()
    profile = get_model_profile(key)
    path = installed_model_path(key)
    if path is None:
        raise RuntimeExecutionError(
            f"Model {key!r} is not installed. Run: locdex model install {key}"
        )

    hardware = hardware or detect_hardware()
    status = runtime_status(hardware)
    if not status.installed or not status.import_ok:
        raise RuntimeExecutionError(
            "llama-cpp-python is not ready. Run: locdex runtime install"
        )
    if not status.healthy:
        raise RuntimeExecutionError(
            f"llama.cpp runtime is unhealthy: {status.reason}"
        )

    backend = status.active_backend or "cpu"
    gpu_layers = -1 if backend in {"cuda", "metal"} else 0
    return InferencePlan(
        model_key=key,
        model_path=str(path),
        backend=backend,
        n_ctx=profile.preferred_context,
        n_threads=_threads_for(hardware),
        n_gpu_layers=gpu_layers,
        max_tokens=max(1, int(max_tokens)),
        temperature=max(0.0, min(2.0, float(temperature))),
    )


def _load_llama(plan: InferencePlan):
    try:
        from llama_cpp import Llama
    except Exception as exc:  # pragma: no cover - depends on optional runtime
        raise RuntimeExecutionError(
            f"Could not import llama_cpp: {exc}"
        ) from exc

    kwargs = {
        "model_path": plan.model_path,
        "n_ctx": plan.n_ctx,
        "n_threads": plan.n_threads,
        "n_gpu_layers": plan.n_gpu_layers,
        "verbose": False,
    }
    try:
        return Llama(**kwargs)
    except Exception as first_exc:
        # Auto-selected GPU backends may fail on a particular model/driver
        # combination. Falling back to CPU is allowed; changing models is not.
        if plan.n_gpu_layers != 0:
            try:
                return Llama(
                    model_path=plan.model_path,
                    n_ctx=plan.n_ctx,
                    n_threads=plan.n_threads,
                    n_gpu_layers=0,
                    verbose=False,
                )
            except Exception as cpu_exc:
                raise RuntimeExecutionError(
                    f"Failed to load model with {plan.backend} and CPU fallback: {cpu_exc}"
                ) from cpu_exc
        raise RuntimeExecutionError(f"Failed to load model: {first_exc}") from first_exc


def _extract_text(response: Any) -> str:
    try:
        choices = response["choices"]
        first = choices[0]
        message = first.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if content is not None:
                return str(content).strip()
        text = first.get("text")
        if text is not None:
            return str(text).strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    raise RuntimeExecutionError("llama.cpp returned an unexpected response shape")


def run_prompt(
    prompt: str,
    *,
    model_key: str | None = None,
    system: str | None = None,
    max_tokens: int = 256,
    temperature: float = 0.1,
) -> dict:
    if not prompt.strip():
        raise RuntimeExecutionError("Prompt cannot be empty.")

    plan = plan_inference(
        model_key=model_key,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    llama = _load_llama(plan)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = llama.create_chat_completion(
            messages=messages,
            max_tokens=plan.max_tokens,
            temperature=plan.temperature,
        )
    except Exception as exc:
        raise RuntimeExecutionError(f"Inference failed: {exc}") from exc

    usage = response.get("usage") if isinstance(response, dict) else None
    return {
        "model": plan.model_key,
        "backend": plan.backend,
        "text": _extract_text(response),
        "usage": usage,
        "plan": plan.to_dict(),
    }
