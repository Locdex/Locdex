from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from .config import load_settings
from .parser import MULTI_FILE_PROMPT, parse_multi_file_response


@dataclass(frozen=True)
class CloudConfig:
    provider: str
    models: tuple[str, ...]
    base_url: str
    api_key: str
    api_key_env: str

    @property
    def enabled(self) -> bool:
        return bool(self.provider and self.models and self.base_url and self.api_key)


_PROVIDER_DEFAULTS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/messages",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
}


def _split_models(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def load_cloud_config() -> CloudConfig:
    """Load the user's cloud provider/model configuration.

    Locdex intentionally has no default cloud provider or model. Cloud fallback is
    disabled until the user explicitly configures both.
    """
    saved = load_settings().get("cloud", {})
    if not isinstance(saved, dict):
        saved = {}

    provider = os.environ.get("LOCDEX_CLOUD_PROVIDER", str(saved.get("provider", ""))).strip().lower()

    raw_models = os.environ.get("LOCDEX_CLOUD_MODELS")
    if raw_models is None:
        raw_models = os.environ.get("LOCDEX_CLOUD_MODEL")
    if raw_models is None:
        saved_models = saved.get("models", [])
        if isinstance(saved_models, str):
            raw_models = saved_models
        elif isinstance(saved_models, list):
            raw_models = ",".join(str(item) for item in saved_models)
        else:
            raw_models = ""
    models = _split_models(raw_models)

    defaults = _PROVIDER_DEFAULTS.get(provider, {})
    base_url = os.environ.get(
        "LOCDEX_CLOUD_BASE_URL",
        str(saved.get("base_url") or defaults.get("base_url") or ""),
    ).strip()

    api_key_env = os.environ.get(
        "LOCDEX_CLOUD_API_KEY_ENV",
        str(saved.get("api_key_env") or defaults.get("api_key_env") or "LOCDEX_CLOUD_API_KEY"),
    ).strip()
    api_key = os.environ.get("LOCDEX_CLOUD_API_KEY", "").strip()
    if not api_key and api_key_env:
        api_key = os.environ.get(api_key_env, "").strip()

    return CloudConfig(
        provider=provider,
        models=models,
        base_url=base_url,
        api_key=api_key,
        api_key_env=api_key_env,
    )


def cloud_status() -> dict:
    config = load_cloud_config()
    return {
        "enabled": config.enabled,
        "provider": config.provider or None,
        "models": list(config.models),
        "base_url": config.base_url or None,
        "api_key_env": config.api_key_env or None,
        "api_key_present": bool(config.api_key),
    }


def _request_openai_compatible(config: CloudConfig, model: str, system_prompt: str, prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.15,
    }
    response = requests.post(
        config.base_url,
        json=payload,
        headers=headers,
        timeout=(10, 120),
    )
    response.raise_for_status()
    message = response.json().get("choices", [{}])[0].get("message", {})
    content = message.get("content", "")
    return content if isinstance(content, str) else ""


def _request_anthropic(config: CloudConfig, model: str, system_prompt: str, prompt: str) -> str:
    headers = {
        "x-api-key": config.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 8192,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = requests.post(
        config.base_url,
        json=payload,
        headers=headers,
        timeout=(10, 120),
    )
    response.raise_for_status()
    blocks = response.json().get("content", [])
    text_parts = [
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(part for part in text_parts if part)


def run_cloud(task: str, context: dict | None = None) -> dict:
    """Use only the cloud provider and model(s) explicitly configured by the user."""
    config = load_cloud_config()
    if not config.provider:
        print("[Cloud Fallback] No cloud provider configured; cloud fallback is disabled.")
        return {"files": []}
    if not config.models:
        print("[Cloud Fallback] No cloud model configured; cloud fallback is disabled.")
        return {"files": []}
    if not config.base_url:
        print("[Cloud Fallback] No cloud API endpoint configured; cloud fallback is disabled.")
        return {"files": []}
    if not config.api_key:
        print(
            f"[Cloud Fallback] API key missing. Set {config.api_key_env or 'LOCDEX_CLOUD_API_KEY'} "
            f"for provider '{config.provider}'."
        )
        return {"files": []}

    system_prompt = (context or {}).get("system_prompt", "")
    prompt = task + MULTI_FILE_PROMPT

    for model in config.models:
        print(f"[Cloud Fallback] Attempting {config.provider}: {model}...")
        try:
            if config.provider == "anthropic":
                content = _request_anthropic(config, model, system_prompt, prompt)
            else:
                # OpenRouter and custom/openai-compatible endpoints use the same
                # chat-completions request shape. Nothing is selected by default.
                content = _request_openai_compatible(config, model, system_prompt, prompt)
            files = parse_multi_file_response(content)
            if files:
                return {
                    "files": files,
                    "model": model,
                    "provider": config.provider,
                }
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            print(f"[Cloud Fallback] Request failed for {config.provider}/{model}: {exc}")

    print("[Cloud Fallback] All user-configured cloud models failed.")
    return {"files": []}
