"""One warm, isolated local inference worker for an interactive Locdex process.

The worker owns llama.cpp state. No model bytes, tools, repository handles,
or cloud credentials pass through this lifecycle controller. Cross-process
persistence is deliberately not attempted: a one-shot CLI task exits normally.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .isolated import IsolatedLlamaCppSession


class WarmModelPool:
    """Preload one selected model and reuse it across sequential agent tasks."""

    def __init__(
        self,
        *,
        session_factory: Callable[..., Any] = IsolatedLlamaCppSession,
    ) -> None:
        self._factory = session_factory
        self._session: Any | None = None
        self._model_key: str | None = None

    @property
    def model_key(self) -> str | None:
        return self._model_key

    @property
    def status(self) -> str:
        if self._session is None:
            return "unloaded"
        return str(self._session.worker_status)

    def start(self, model_key: str) -> Any:
        """Begin cold initialization asynchronously; return without waiting for ready."""
        if (
            self._session is not None
            and self._model_key == model_key
            and self._session.worker_status in {"loading", "ready"}
        ):
            return self._session

        self.close()
        session = self._factory(model_key=model_key)
        try:
            session.preload()
        except BaseException:
            session.close()
            raise
        self._model_key = model_key
        self._session = session
        return session

    def for_task(
        self, model_key: str, *,
        cancelled: Callable[[], bool] | None,
        progress: Callable[[str], None] | None,
        prefer_cloud_fallback: bool = False,
    ) -> Any:
        """Reuse a warm worker while switching per-task cancellation/UI callbacks."""
        session = self.start(model_key)
        session.configure_task(
            cancelled=cancelled,
            progress=progress,
            prefer_cloud_fallback=prefer_cloud_fallback,
        )
        return session

    def release_task(self, session: Any) -> None:
        """Discard callbacks without unloading a healthy model between tasks."""
        if self._session is session and not session.closed:
            session.configure_task(cancelled=None, progress=None)

    def close(self) -> None:
        session, self._session = self._session, None
        self._model_key = None
        if session is not None:
            session.close()
