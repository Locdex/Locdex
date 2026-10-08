from __future__ import annotations

import json

import pytest

from locdex.providers import openai_compatible as providers


class Response:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP request failed")

    def json(self):
        return self.data


def test_provider_catalog_and_aliases():
    catalog = {row["name"]: row for row in providers.available_providers()}
    assert set(catalog) >= {"openai", "anthropic", "gemini", "groq", "openrouter", "deepseek", "custom"}
    assert catalog["anthropic"]["api_type"] == "anthropic-messages"
    assert providers.normalize_provider("openapi") == "openai"


@pytest.mark.parametrize(
    "name,key_var,base",
    [
        ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1"),
        ("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1"),
        ("gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
        ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
        ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    ],
)
def test_config_uses_provider_specific_keys(monkeypatch, name, key_var, base):
    for key in ("LOCDEX_CLOUD_API_KEY", "LOCDEX_CLOUD_BASE_URL", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LOCDEX_CLOUD_ENABLED", "1")
    monkeypatch.setenv("LOCDEX_CLOUD_PROVIDER", name)
    monkeypatch.setenv("LOCDEX_CLOUD_MODEL", "user-chosen-model")
    monkeypatch.setenv(key_var, "secret")
    config = providers.CloudConfig.from_env()
    assert config.enabled
    assert config.base_url == base
    assert config.api_key == "secret"
    assert "secret" not in json.dumps(config.public_dict())


def test_anthropic_native_messages_forced_structured_decision(monkeypatch):
    config = providers.CloudConfig(
        True, "anthropic", "claude-selected-by-user",
        "https://api.anthropic.com/v1", "secret",
    )
    observed = []
    def post(url, *, headers, json, timeout):
        observed.append((url, headers, json, timeout))
        return Response({
            "content": [{"type": "tool_use", "name": "locdex_agent_action",
                         "input": {"action": "final", "summary": "done"}}],
            "usage": {"input_tokens": 45, "output_tokens": 12},
        })

    monkeypatch.setattr(providers.requests, "post", post)
    session = providers.make_cloud_session(config)
    assert isinstance(session, providers.AnthropicMessagesSession)
    result = session.json_completion(
        [
            {"role": "system", "content": "Rules"},
            {"role": "user", "content": "Fix function"},
            {"role": "assistant", "content": "I will inspect"},
            {"role": "user", "content": "Here is an error"},
        ],
        {"type": "object", "properties": {"action": {"type": "string"}}},
    )
    assert result["action"] == "final"
    url, headers, body, _ = observed[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "secret"
    assert headers["anthropic-version"]
    assert body["system"] == "Rules"
    assert body["tool_choice"] == {"type": "tool", "name": "locdex_agent_action"}
    assert body["tools"][0]["input_schema"]["type"] == "object"
    assert session.input_tokens == 45
    assert session.output_tokens == 12


def test_anthropic_rejects_missing_tool_output(monkeypatch):
    config = providers.CloudConfig(True, "anthropic", "a", "https://api.anthropic.com/v1", "secret")
    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: Response({"content": [{"type": "text", "text": "done"}]}))
    with pytest.raises(RuntimeError, match="did not return"):
        providers.AnthropicMessagesSession(config).json_completion([{"role": "user", "content": "fix"}], {"type": "object"})


def test_openai_reasoning_model_uses_compatible_parameters(monkeypatch):
    config = providers.CloudConfig(True, "openai", "gpt-6", "https://api.openai.com/v1", "secret")
    captured = []
    def post(url, *, headers, json, timeout):
        captured.append(json)
        return Response({"choices": [{"message": {"content": '{"action":"final"}'}}],
                         "usage": {"prompt_tokens": 30, "completion_tokens": 5}})
    monkeypatch.setattr(providers.requests, "post", post)
    result = providers.make_cloud_session(config).json_completion([{"role": "user", "content": "Test JSON"}], {"type": "object"})
    assert result == {"action": "final"}
    assert captured[0]["max_completion_tokens"] == 512
    assert "temperature" not in captured[0]
    assert captured[0]["response_format"]["type"] == "json_schema"


def test_openai_compatible_falls_back_to_json_only_after_schema_rejection(monkeypatch):
    config = providers.CloudConfig(True, "groq", "selected", "https://api.groq.com/openai/v1", "secret")
    captured = []
    def post(url, *, headers, json, timeout):
        captured.append(json)
        if len(captured) == 1:
            return Response({}, 400)
        return Response({"choices": [{"message": {"content": '{"action":"final"}'}}]})
    monkeypatch.setattr(providers.requests, "post", post)
    assert providers.make_cloud_session(config).json_completion(
        [{"role": "user", "content": "Test JSON"}], {"type": "object"}
    )["action"] == "final"
    assert "response_format" not in captured[1]
    assert "Schema:" in captured[1]["messages"][-1]["content"]


def test_cloud_status_does_not_echo_auth_in_url():
    config = providers.CloudConfig(
        True, "custom", "model", "https://user:password@provider.example/v1?token=secret", "secret",
    )
    public = json.dumps(config.public_dict())
    assert "password" not in public
    assert "token=secret" not in public
    assert "api_key" not in public.replace('"api_key_configured"', "")
