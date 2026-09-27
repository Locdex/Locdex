from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from platformdirs import user_cache_dir, user_config_dir
except ImportError:  # pragma: no cover
    user_cache_dir = None
    user_config_dir = None

from .model_profiles import DEFAULT_MODEL_KEY, ModelProfile, get_model_profile


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def locdex_cache_dir() -> Path:
    if user_cache_dir is None:
        default = Path.home() / ".cache" / "locdex"
    else:
        default = Path(user_cache_dir("locdex", "Locdex"))
    return Path(os.environ.get("LOCDEX_CACHE_DIR", str(default))).expanduser().resolve()


def locdex_config_dir() -> Path:
    if user_config_dir is None:
        default = Path.home() / ".config" / "locdex"
    else:
        default = Path(user_config_dir("locdex", "Locdex"))
    return Path(os.environ.get("LOCDEX_CONFIG_DIR", str(default))).expanduser().resolve()


def _settings_path() -> Path:
    return locdex_config_dir() / "settings.json"


def load_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def selected_model_key() -> str:
    env_choice = os.environ.get("LOCDEX_MODEL")
    if env_choice:
        return get_model_profile(env_choice).key
    saved = str(load_settings().get("model", DEFAULT_MODEL_KEY))
    try:
        return get_model_profile(saved).key
    except ValueError:
        return DEFAULT_MODEL_KEY


def select_model(key: str) -> str:
    profile = get_model_profile(key)
    settings = load_settings()
    settings["model"] = profile.key
    save_settings(settings)
    return profile.key


@dataclass(frozen=True)
class LocalModelConfig:
    model_key: str
    repo_id: str
    filename_pattern: str
    revision: str | None
    expected_sha256: str | None
    explicit_model_path: Path | None
    cache_dir: Path
    auto_download: bool
    n_ctx: int
    n_threads: int
    n_gpu_layers: int | None
    max_tokens: int
    temperature: float
    max_agent_steps: int

    @property
    def profile(self) -> ModelProfile:
        return get_model_profile(self.model_key)


def load_local_model_config(model_key: str | None = None) -> LocalModelConfig:
    profile = get_model_profile(model_key or selected_model_key())
    explicit = os.environ.get("LOCDEX_MODEL_PATH")
    explicit_path = Path(explicit).expanduser().resolve() if explicit else None

    cpu_count = os.cpu_count() or 4
    raw_gpu_layers = os.environ.get("LOCDEX_N_GPU_LAYERS")
    gpu_layers: int | None
    if raw_gpu_layers is None or raw_gpu_layers.strip().lower() == "auto":
        gpu_layers = None
    else:
        try:
            gpu_layers = int(raw_gpu_layers)
        except ValueError:
            gpu_layers = None

    default_agent_steps = 20 if profile.key == "smoke" else 12

    return LocalModelConfig(
        model_key=profile.key,
        repo_id=os.environ.get("LOCDEX_MODEL_REPO", profile.repo_id).strip(),
        filename_pattern=os.environ.get("LOCDEX_MODEL_PATTERN", profile.filename_pattern).strip(),
        revision=(os.environ.get("LOCDEX_MODEL_REVISION") or None),
        expected_sha256=(os.environ.get("LOCDEX_MODEL_SHA256") or profile.expected_sha256),
        explicit_model_path=explicit_path,
        cache_dir=locdex_cache_dir(),
        auto_download=_env_bool("LOCDEX_AUTO_DOWNLOAD", True),
        n_ctx=max(2048, _env_int("LOCDEX_N_CTX", 16384)),
        n_threads=max(1, _env_int("LOCDEX_N_THREADS", max(1, cpu_count - 1))),
        n_gpu_layers=gpu_layers,
        max_tokens=max(512, _env_int("LOCDEX_MAX_TOKENS", 8192)),
        temperature=max(0.0, min(2.0, _env_float("LOCDEX_TEMPERATURE", 0.15))),
        max_agent_steps=max(2, min(30, _env_int("LOCDEX_MAX_AGENT_STEPS", default_agent_steps))),
    )
