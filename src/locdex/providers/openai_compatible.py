from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests


_TRUTHY = {"1", "true", "yes", "on"}

# Built-in endpoints; no provider's model/version is forced on the user.
# Custom OpenAI-compatible providers continue to use LOCDEX_CLOUD_BASE_URL.
PROVIDER_PRESETS: dict[str, tuple[str, str, str]] = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "openai-compatible"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "anthropic-messages"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "openai-compatible"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai-compatible"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "openai-compatible"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY", "openai-compatible"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY", "openai-compatible"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "openai-compatible"),
}
ALIASES = {"openapi": "openai", "google": "gemini", "claude": "anthropic"}


def normalize_provider(name: str) -> str:
    value = name.strip().lower()
    return ALIASES.get(value, value or "custom")


def available_providers() -> list[dict[str, str]]:
    return [
        {"name": key, "api_type": kind, "base_url": url, "key_environment": key_env}
        for key, (url, key_env, kind) in sorted(PROVIDER_PRESETS.items())
    ] + [
        {
            "name": "custom",
            "api_type": "openai-compatible",
            "base_url": "(LOCDEX_CLOUD_BASE_URL required)",
            "key_environment": "LOCDEX_CLOUD_API_KEY",
        }
    ]


def _public_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return "(invalid URL)"


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
        selected = normalize_provider(os.environ.get("LOCDEX_CLOUD_PROVIDER", "custom"))
        preset = PROVIDER_PRESETS.get(selected)
        enabled = os.environ.get("LOCDEX_CLOUD_ENABLED", "").strip().lower() in _TRUTHY
        model = os.environ.get("LOCDEX_CLOUD_MODEL", "").strip()
        base = os.environ.get("LOCDEX_CLOUD_BASE_URL", "").strip().rstrip("/")
        base_url = base or (preset[0] if preset else "")
        key_var = preset[1] if preset else "LOCDEX_CLOUD_API_KEY"
        # An explicit generic API key has highest priority and preserves
        # compatibility with existing Locdex installations.
        api_key = (os.environ.get("LOCDEX_CLOUD_API_KEY", "")
                   or os.environ.get(key_var, "")
                   or (os.environ.get("GOOGLE_API_KEY", "") if selected == "gemini" else "")).strip()

        def _float(name: str) -> float:
            try:
                return max(0.0, float(os.environ.get(name, "").strip() or 0))
            except ValueError:
                return 0.0

        def _int(name: str, default: int) -> int:
            try:
                return max(4096, int(os.environ.get(name, "").strip() or default))
            except ValueError:
                return default

        return cls(
            enabled=enabled and bool(model and base_url and api_key),
            provider=selected,
            model=model,
            base_url=base_url,
            api_key=api_key,
            input_cost_per_million=_float("LOCDEX_CLOUD_INPUT_COST_PER_MILLION"),
            output_cost_per_million=_float("LOCDEX_CLOUD_OUTPUT_COST_PER_MILLION"),
            context_limit=_int("LOCDEX_CLOUD_CONTEXT_LIMIT", 128000),
        )

    @property
    def api_type(self) -> str:
        return PROVIDER_PRESETS.get(self.provider, ("", "", "openai-compatible"))[2]

    def public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "api_type": self.api_type,
            "model": self.model or None,
            "base_url": _public_url(self.base_url) if self.base_url else None,
            "api_key_configured": bool(self.api_key),
            "input_cost_per_million": self.input_cost_per_million,
            "output_cost_per_million": self.output_cost_per_million,
            "context_limit": self.context_limit,
        }


class _CloudUsage:
    def __init__(self, config: CloudConfig, timeout: float = 120.0) -> None:
        if not config.enabled:
            raise ValueError("Cloud execution is not configured or enabled.")
        self.config = config
        self.timeout = timeout
        self.input_tokens = 0
        self.output_tokens = 0
        self.latency_ms = 0.0
        self.cost_usd = 0.0

    def _usage(self, prompt_tokens: int, completion_tokens: int, elapsed_ms: float) -> None:
        self.input_tokens += max(0, int(prompt_tokens))
        self.output_tokens += max(0, int(completion_tokens))
        self.latency_ms += elapsed_ms
        self.cost_usd += (
            (max(0, int(prompt_tokens)) / 1_000_000) * self.config.input_cost_per_million
            + (max(0, int(completion_tokens)) / 1_000_000) * self.config.output_cost_per_million
        )


def _reasoning_model(model: str) -> bool:
    lowered = model.lower()
    return lowered.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


class OpenAICompatibleSession(_CloudUsage):
    """OpenAI Chat Completions schema with a bounded JSON-only fallback.

    Other vendors implement subsets; retry without response_format only after
    provider rejects that format (400/422), not on authentication failure.
    """

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
        }
        if self.config.provider == "openai" and _reasoning_model(self.config.model):
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens
            payload["temperature"] = temperature

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
                {"role": "user", "content": (
                    "Return ONLY valid JSON conforming to the Locdex agent-action "
                    "schema. No explanation or markdown. JSON object required. "
                    "Schema: " + json.dumps(schema, separators=(",", ":"))[:10000]
                )},
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
            return "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("text")
            )
        raise RuntimeError("Cloud provider returned no textual JSON response.")

    def json_completion(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *,
        max_tokens: int = 512, temperature: float = 0.0,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        payload = self._payload(
            messages, schema, max_tokens=max_tokens,
            temperature=temperature, include_schema=True,
        )
        response = self._request(payload)
        if response.status_code in {400, 422}:
            payload = self._payload(
                messages, schema, max_tokens=max_tokens,
                temperature=temperature, include_schema=False,
            )
            response = self._request(payload)
        response.raise_for_status()
        elapsed_ms = (time.perf_counter() - started) * 1000
        data = response.json()
        usage = data.get("usage") or {}
        self._usage(
            usage.get("prompt_tokens") or 0,
            usage.get("completion_tokens") or 0,
            elapsed_ms,
        )
        raw = self._extract_content(data).strip()
        if raw.startswith("```"):
            parts = raw.splitlines()
            raw = "\n".join(
                parts[1:-1] if parts[-1].strip() == "```" else parts[1:]
            ).strip()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise RuntimeError("Cloud provider returned non-object JSON.")
        return result


class AnthropicMessagesSession(_CloudUsage):
    """Native Anthropic Messages: forced structured tool use, not Chat Completions."""

    def _payload(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *,
        max_tokens: int,
    ) -> dict[str, Any]:
        system: list[str] = []
        turns: list[dict[str, str]] = []
        for msg in messages:
            role = str(msg.get("role", "user"))
            content = str(msg.get("content", ""))
            if role in {"system", "developer"}:
                system.append(content)
            elif role in {"user", "assistant"}:
                # Anthropic rejects some repeated-role sequences; merge adjacent turns.
                if turns and turns[-1]["role"] == role:
                    turns[-1]["content"] += "\n\n" + content
                else:
                    turns.append({"role": role, "content": content})
        if not turns:
            turns.append({"role": "user", "content": "Return a Locdex agent decision."})
        if turns[0]["role"] != "user":
            turns.insert(0, {"role": "user", "content": "Follow the system instructions."})
        return {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": "\n\n".join(system) or "Return valid Locdex agent actions.",
            "messages": turns,
            "tools": [{
                "name": "locdex_agent_action",
                "description": "Return exactly one structured Locdex agent decision.",
                "input_schema": schema,
            }],
            "tool_choice": {"type": "tool", "name": "locdex_agent_action"},
        }

    def json_completion(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *,
        max_tokens: int = 512, temperature: float = 0.0,
    ) -> dict[str, Any]:
        payload = self._payload(messages, schema, max_tokens=max_tokens)
        started = time.perf_counter()
        response = requests.post(
            f"{self.config.base_url}/messages",
            headers={
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "user-agent": "locdex-anthropic/1",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        elapsed_ms = (time.perf_counter() - started) * 1000
        data = response.json()
        usage = data.get("usage") or {}
        self._usage(
            usage.get("input_tokens") or 0,
            usage.get("output_tokens") or 0,
            elapsed_ms,
        )
        for block in data.get("content", []):
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "locdex_agent_action"
                and isinstance(block.get("input"), dict)
            ):
                return block["input"]
        raise RuntimeError("Anthropic did not return a Locdex tool-use decision.")


def make_cloud_session(config: CloudConfig) -> _CloudUsage:
    if config.provider == "anthropic":
        return AnthropicMessagesSession(config)
    return OpenAICompatibleSession(config)
