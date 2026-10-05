from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests


_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CloudConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str
    api_key: str
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0
    context_limit: int = 128000

    @classmethod
    def from_env(cls) -> "CloudConfig":
        enabled = os.environ.get("LOCDEX_CLOUD_ENABLED", "").strip().lower() in _TRUTHY
        provider = os.environ.get("LOCDEX_CLOUD_PROVIDER", "configured").strip() or "configured"
        model = os.environ.get("LOCDEX_CLOUD_MODEL", "").strip()
        base_url = os.environ.get("LOCDEX_CLOUD_BASE_URL", "").strip().rstrip("/")
        api_key = os.environ.get("LOCDEX_CLOUD_API_KEY", "").strip()

        def _float(name: str) -> float:
            raw = os.environ.get(name, "").strip()
            if not raw:
                return 0.0
            try:
                return max(0.0, float(raw))
            except ValueError:
                return 0.0

        def _int(name: str, default: int) -> int:
            raw = os.environ.get(name, "").strip()
            if not raw:
                return default
            try:
                return max(4096, int(raw))
            except ValueError:
                return default

        return cls(
            enabled=enabled and bool(model and base_url and api_key),
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            input_cost_per_million=_float("LOCDEX_CLOUD_INPUT_COST_PER_MILLION"),
            output_cost_per_million=_float("LOCDEX_CLOUD_OUTPUT_COST_PER_MILLION"),
            context_limit=_int("LOCDEX_CLOUD_CONTEXT_LIMIT", 128000),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model or None,
            "base_url": self.base_url or None,
            "api_key_configured": bool(self.api_key),
            "input_cost_per_million": self.input_cost_per_million,
            "output_cost_per_million": self.output_cost_per_million,
            "context_limit": self.context_limit,
        }


class OpenAICompatibleSession:
    def __init__(self, config: CloudConfig, *, timeout: float = 120.0):
        if not config.enabled:
            raise ValueError("Cloud execution is not configured or enabled.")
        self.config = config
        self.timeout = timeout
        self.input_tokens = 0
        self.output_tokens = 0
        self.latency_ms = 0.0
        self.cost_usd = 0.0

    def _payload(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        max_tokens: int,
        temperature: float,
        include_schema: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if include_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "locdex_agent_action",
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            payload["messages"] = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "Return only one JSON object that conforms exactly to "
                        "the supplied Locdex agent action schema."
                    ),
                },
            ]
        return payload

    def _request(self, payload: dict[str, Any]) -> requests.Response:
        return requests.post(
            f"{self.config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "locdex-cloud/1",
            },
            json=payload,
            timeout=self.timeout,
        )

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Cloud provider returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("text")
            ]
            return "".join(parts)
        raise RuntimeError("Cloud provider returned no textual JSON response.")

    def json_completion(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        payload = self._payload(
            messages,
            schema,
            max_tokens=max_tokens,
            temperature=temperature,
            include_schema=True,
        )
        response = self._request(payload)
        if response.status_code in {400, 404, 422}:
            payload = self._payload(
                messages,
                schema,
                max_tokens=max_tokens,
                temperature=temperature,
                include_schema=False,
            )
            response = self._request(payload)
        response.raise_for_status()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        data = response.json()

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        self.input_tokens += prompt_tokens
        self.output_tokens += completion_tokens
        self.latency_ms += elapsed_ms
        self.cost_usd += (
            (prompt_tokens / 1_000_000.0) * self.config.input_cost_per_million
            + (completion_tokens / 1_000_000.0) * self.config.output_cost_per_million
        )

        raw = self._extract_content(data).strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("Cloud provider returned non-object JSON.")
        return parsed
