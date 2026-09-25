from __future__ import annotations

import json
import threading
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import LocalModelConfig, load_local_model_config
from .model_manager import ensure_model
from .runtime_manager import effective_hardware_profile


class LocalRuntimeError(RuntimeError):
    pass


class EmbeddedLlamaRuntime:
    """Locdex-owned GGUF runtime with automatic accelerator selection and CPU fallback."""

    def __init__(self, model_path: Path, config: LocalModelConfig):
        try:
            from llama_cpp import Llama
        except ImportError as exc:  # pragma: no cover
            raise LocalRuntimeError(
                "Locdex local runtime is not installed. Run `locdex setup` or `locdex runtime install`."
            ) from exc

        profile = effective_hardware_profile()
        requested_layers = config.n_gpu_layers
        gpu_layers = profile.auto_gpu_layers if requested_layers is None else requested_layers
        self._lock = threading.RLock()
        self.config = config
        self.model_path = model_path
        self.backend = profile.backend if gpu_layers != 0 else "cpu"

        kwargs = {
            "model_path": str(model_path),
            "n_ctx": config.n_ctx,
            "n_threads": config.n_threads,
            "n_gpu_layers": gpu_layers,
            "verbose": False,
        }
        try:
            self._llm = Llama(**kwargs)
        except Exception as exc:
            # A driver/runtime mismatch should not make Locdex unusable. Retry once
            # on CPU when automatic GPU offload was selected.
            if gpu_layers != 0 and requested_layers is None:
                print(f"[Locdex runtime] {profile.backend} load failed; retrying on CPU: {exc}")
                kwargs["n_gpu_layers"] = 0
                try:
                    self._llm = Llama(**kwargs)
                    self.backend = "cpu-fallback"
                except Exception as cpu_exc:
                    raise LocalRuntimeError(f"Failed to load local GGUF model: {cpu_exc}") from cpu_exc
            else:
                raise LocalRuntimeError(f"Failed to load local GGUF model: {exc}") from exc

    def json_completion(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                response = self._llm.create_chat_completion(
                    messages=messages,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    response_format={"type": "json_object", "schema": schema},
                )
                content = response["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise LocalRuntimeError("Local model returned a non-text response.")
                return json.loads(content)
            except LocalRuntimeError:
                raise
            except Exception as exc:
                raise LocalRuntimeError(f"Local inference failed: {exc}") from exc


@lru_cache(maxsize=4)
def _runtime_for_key(model_path: str, config: LocalModelConfig) -> EmbeddedLlamaRuntime:
    return EmbeddedLlamaRuntime(Path(model_path), config)


def get_runtime(config: LocalModelConfig | None = None) -> EmbeddedLlamaRuntime:
    config = config or load_local_model_config()
    model_path = ensure_model(config)
    return _runtime_for_key(str(model_path), config)


def smoke_test_runtime(config: LocalModelConfig | None = None) -> dict:
    config = config or load_local_model_config()
    # Setup only needs to prove that the model can load and produce constrained
    # output; a small context avoids allocating the normal coding-session KV cache.
    smoke_config = replace(config, n_ctx=min(config.n_ctx, 2048), max_tokens=64)
    runtime = get_runtime(smoke_config)
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    result = runtime.json_completion(
        [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": 'Return exactly {"ok": true}.'},
        ],
        schema,
    )
    if result.get("ok") is not True:
        raise LocalRuntimeError(f"Runtime smoke test returned an unexpected response: {result}")
    return {"ok": True, "backend": runtime.backend, "model": smoke_config.model_key}
