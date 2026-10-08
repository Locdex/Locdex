from __future__ import annotations

import multiprocessing
import os
import time
from multiprocessing.connection import Connection
from typing import Any, Callable

from .llama_cpp import LlamaCppSession, RuntimeExecutionError


def _model_process(connection: Connection, model_key: str) -> None:
    """The child owns native llama.cpp state. A timeout can terminate it safely."""
    try:
        session = LlamaCppSession(model_key=model_key)
        connection.send(("ready", None))
        while True:
            request = connection.recv()
            if request is None:
                break
            messages, schema, options = request
            try:
                value = session.json_completion(messages, schema, **options)
                connection.send(("ok", value))
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
    ):
        self.model_key = model_key
        self.cancelled = cancelled or (lambda: False)
        self.progress = progress
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else _timeout_from_env()
        self._parent: Connection | None = None
        self._process: multiprocessing.Process | None = None
        self._closed = False

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
        deadline = time.monotonic() + self.timeout_seconds
        self._ensure_started()
        assert self._parent is not None
        if not getattr(self, "_ready", False):
            self._announce("[Inference] Loading local model...")
            kind, payload = self._receive(deadline, "loading model")
            if kind != "ready":
                self.close()
                raise RuntimeExecutionError(str(payload)[:350])
            self._ready = True
        if self.cancelled():
            self.close()
            raise RuntimeExecutionError("Local inference cancelled.")
        self._announce("[Inference] Generating model decision...")
        try:
            self._parent.send((messages, schema, kwargs))
        except (BrokenPipeError, OSError) as exc:
            self.close()
            raise RuntimeExecutionError("Could not send request to local model process.") from exc
        kind, payload = self._receive(deadline, "generating")
        if kind != "ok":
            raise RuntimeExecutionError(str(payload)[:350])
        if not isinstance(payload, dict):
            raise RuntimeExecutionError("Local inference returned a non-object response.")
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
