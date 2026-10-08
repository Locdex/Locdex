from __future__ import annotations

import multiprocessing
import os
import time
from multiprocessing.connection import Connection
from typing import Any, Callable

from .llama_cpp import LlamaCppSession, RuntimeExecutionError
from .timeout_policy import (
    estimate_inference_timeout,
    record_generation_speed,
    record_inference_timeout,
)
from .hardware import detect_hardware


def _model_process(connection: Connection, model_key: str) -> None:
    """The child owns native llama.cpp state. A timeout can terminate it safely."""
    try:
        started = time.monotonic()
        session = LlamaCppSession(model_key=model_key)
        connection.send(("ready", {"loading_seconds": time.monotonic() - started}))
        while True:
            request = connection.recv()
            if request is None:
                break
            if isinstance(request, dict) and request.get("kind") == "prompt":
                try:
                    started = time.monotonic()
                    messages = [{"role": "user", "content": str(request["prompt"])}]
                    answer = session.chat(
                        messages,
                        max_tokens=int(request.get("max_tokens", 32)),
                        temperature=0.0,
                    )
                    connection.send(("prompt", {
                        "text": answer["text"],
                        "usage": answer.get("usage"),
                        "backend": session.plan.backend,
                        "seconds": time.monotonic() - started,
                    }))
                except Exception as exc:
                    connection.send(("error", f"{type(exc).__name__}: {str(exc)[:300]}"))
                continue
            messages, schema, options = request
            try:
                started = time.monotonic()
                value = session.json_completion(messages, schema, **options)
                usage = getattr(session, "last_usage", {}) or {}
                connection.send(("ok", {
                    "result": value,
                    "seconds": time.monotonic() - started,
                    "output_tokens": usage.get("completion_tokens", 0),
                }))
            except Exception as exc:
                connection.send(("error", f"{type(exc).__name__}: {str(exc)[:300]}"))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send(("error", f"Model startup failed: {type(exc).__name__}: {str(exc)[:300]}"))
        except (OSError, BrokenPipeError):
            pass
    finally:
        connection.close()


def _timeout_from_env() -> float:
    try:
        return max(20.0, min(600.0, float(os.environ.get("LOCDEX_INFERENCE_TIMEOUT_SECONDS", "90"))))
    except ValueError:
        return 90.0


class IsolatedLlamaCppSession:
    """Windows-safe native model execution with a hard timeout and cancellation.

    One spawned model process is reused across turns in a task. No repository
    access or tool permission authority lives in the inference child.
    """

    def __init__(
        self,
        *,
        model_key: str,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[str], None] | None = None,
        timeout_seconds: float | None = None,
        prefer_cloud_fallback: bool = False,
    ):
        self.model_key = model_key
        self.cancelled = cancelled or (lambda: False)
        self.progress = progress
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else _timeout_from_env()
        self._explicit_timeout = timeout_seconds
        self.prefer_cloud_fallback = prefer_cloud_fallback
        self.hardware = detect_hardware() if timeout_seconds is None else None
        self._parent: Connection | None = None
        self._process: multiprocessing.Process | None = None
        self._closed = False
        self._calibration_backend: str | None = None

    def _announce(self, text: str) -> None:
        if self.progress is not None:
            self.progress(text)

    def _ensure_started(self) -> None:
        if self._parent is not None:
            return
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        process = ctx.Process(
            target=_model_process,
            args=(child, self.model_key),
            daemon=True,
            name="locdex-local-inference",
        )
        try:
            process.start()
        except Exception:
            parent.close()
            child.close()
            raise
        child.close()
        self._parent = parent
        self._process = process

    def _receive(self, deadline: float, phase: str) -> tuple[str, Any]:
        assert self._parent is not None
        assert self._process is not None
        last_note = time.monotonic()
        while True:
            if self.cancelled():
                self.close()
                raise RuntimeExecutionError("Local inference cancelled; model process stopped.")
            now = time.monotonic()
            if now >= deadline:
                if self._calibration_backend is not None:
                    # A timeout is a lower bound, not a measured token rate.
                    # Persist it locally so the next run doesn't use the same
                    # unrealistically short deadline on this machine.
                    try:
                        record_inference_timeout(
                            self.model_key,
                            self._calibration_backend,
                            phase=phase,
                            seconds=self.timeout_seconds,
                        )
                    except (OSError, ValueError):
                        pass
                self.close()
                raise RuntimeExecutionError(
                    f"Local inference {phase} timed out after {self.timeout_seconds:g}s; "
                    "model process terminated. Set LOCDEX_INFERENCE_TIMEOUT_SECONDS "
                    "to a larger value if your hardware requires longer."
                )
            if self._parent.poll(min(0.2, deadline - now)):
                try:
                    return self._parent.recv()
                except EOFError as exc:
                    self.close()
                    raise RuntimeExecutionError("Local inference process exited unexpectedly.") from exc
            if not self._process.is_alive():
                self.close()
                raise RuntimeExecutionError("Local inference process crashed or exited unexpectedly.")
            if now - last_note >= 15:
                self._announce(f"[Inference] Still {phase} ({int(now - (deadline - self.timeout_seconds))}s); timeout active")
                last_note = now

    def json_completion(self, messages: list[dict[str, str]], schema: dict[str, Any], **kwargs: Any) -> dict:
        if self._closed:
            raise RuntimeExecutionError("Local inference session has already been closed.")
        # A load budget and a generation budget are independent. The 12-step
        # agent cap alone cannot interrupt native inference.
        estimated_prompt = sum(
            len(str(message.get("content", ""))) // 4
            for message in messages
        )
        budget = (
            estimate_inference_timeout(
                self.model_key,
                hardware=self.hardware,
                max_tokens=int(kwargs.get("max_tokens", 512)),
                prompt_tokens=estimated_prompt,
                prefer_cloud_fallback=self.prefer_cloud_fallback,
            )
            if self._explicit_timeout is None
            else None
        )
        self._calibration_backend = budget.backend if budget is not None else None
        load_limit = (
            self._explicit_timeout if budget is None else budget.load_seconds
        )
        generate_limit = (
            self._explicit_timeout if budget is None else budget.generate_seconds
        )
        self.timeout_seconds = load_limit
        self._ensure_started()
        assert self._parent is not None
        if not getattr(self, "_ready", False):
            self._announce(
                f"[Inference] Loading {self.model_key}; deadline {load_limit:g}s"
            )
            kind, payload = self._receive(
                time.monotonic() + load_limit, "loading model"
            )
            if kind != "ready":
                self.close()
                raise RuntimeExecutionError(str(payload)[:350])
            self._ready = True
        if self.cancelled():
            self.close()
            raise RuntimeExecutionError("Local inference cancelled.")
        self.timeout_seconds = generate_limit
        self._announce(
            f"[Inference] Generating {self.model_key}; deadline "
            f"{generate_limit:g}s"
            + (
                f" ({budget.source})" if budget is not None else " (manual override)"
            )
        )
        try:
            self._parent.send((messages, schema, kwargs))
        except (BrokenPipeError, OSError) as exc:
            self.close()
            raise RuntimeExecutionError("Could not send request to local model process.") from exc
        kind, payload = self._receive(
            time.monotonic() + generate_limit, "generating"
        )
        if kind != "ok":
            raise RuntimeExecutionError(str(payload)[:350])
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            raise RuntimeExecutionError("Local inference returned a non-object response.")
        if budget is not None:
            try:
                record_generation_speed(
                    self.model_key,
                    budget.backend,
                    seconds=float(payload.get("seconds", 0)),
                    output_tokens=int(payload.get("output_tokens", 0)),
                )
            except (TypeError, ValueError, OverflowError):
                pass
        return payload["result"]

    def __enter__(self) -> "IsolatedLlamaCppSession":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

    def prompt_completion(self, prompt: str, *, max_tokens: int = 32) -> dict:
        """Run qualification's plain-text prompt in the same killable child."""
        if self._closed:
            raise RuntimeExecutionError("Local inference session has already been closed.")
        budget = (
            estimate_inference_timeout(
                self.model_key,
                hardware=self.hardware,
                max_tokens=max_tokens,
                prompt_tokens=len(prompt) // 4,
                prefer_cloud_fallback=False,
            )
            if self._explicit_timeout is None else None
        )
        self._calibration_backend = budget.backend if budget is not None else None
        load_limit = self._explicit_timeout if budget is None else budget.load_seconds
        generation_limit = self._explicit_timeout if budget is None else budget.generate_seconds
        self.timeout_seconds = load_limit
        self._ensure_started()
        assert self._parent is not None
        if not getattr(self, "_ready", False):
            self._announce(f"[Inference] Loading {self.model_key}; deadline {load_limit:g}s")
            kind, payload = self._receive(
                time.monotonic() + load_limit, "loading model"
            )
            if kind != "ready":
                self.close()
                raise RuntimeExecutionError(str(payload)[:350])
            self._ready = True
        self.timeout_seconds = generation_limit
        self._announce(f"[Inference] Checking model prompt; deadline {generation_limit:g}s")
        self._parent.send({
            "kind": "prompt", "prompt": prompt, "max_tokens": max_tokens,
        })
        kind, payload = self._receive(
            time.monotonic() + generation_limit, "generating"
        )
        if kind != "prompt" or not isinstance(payload, dict):
            raise RuntimeExecutionError(str(payload)[:350])
        return payload

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._parent is not None:
            try:
                self._parent.send(None)
            except (OSError, BrokenPipeError):
                pass
        if self._process is not None:
            self._process.join(timeout=0.3)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=1.0)
        if self._parent is not None:
            self._parent.close()
        self._parent = None
        self._process = None
