from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from platformdirs import user_cache_dir, user_config_dir

from .profiles import DEFAULT_MODEL_KEY, MODEL_PROFILES, ModelProfile, get_model_profile


class ModelInstallError(RuntimeError):
    pass


def _cache_dir() -> Path:
    return Path(os.environ.get("LOCDEX_CACHE_DIR", user_cache_dir("locdex", "Locdex"))).expanduser().resolve()


def _config_dir() -> Path:
    return Path(os.environ.get("LOCDEX_CONFIG_DIR", user_config_dir("locdex", "Locdex"))).expanduser().resolve()


def _settings_path() -> Path:
    return _config_dir() / "settings.json"


def _manifest_path(key: str) -> Path:
    return _cache_dir() / "manifests" / f"{key}.json"


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def selected_model_key() -> str:
    env_choice = os.environ.get("LOCDEX_MODEL")
    if env_choice:
        return get_model_profile(env_choice).key
    saved = str(_load_json(_settings_path()).get("model", DEFAULT_MODEL_KEY))
    try:
        return get_model_profile(saved).key
    except ValueError:
        return DEFAULT_MODEL_KEY


def select_model(key: str) -> str:
    profile = get_model_profile(key)
    settings = _load_json(_settings_path())
    settings["model"] = profile.key
    _save_json(_settings_path(), settings)
    return profile.key


def _sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(key: str) -> dict:
    return _load_json(_manifest_path(key))


def installed_model_path(key: str) -> Path | None:
    explicit = os.environ.get("LOCDEX_MODEL_PATH")
    if explicit and get_model_profile(key).key == selected_model_key():
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.is_file() else None

    manifest = _manifest(key)
    candidate = Path(str(manifest.get("path", ""))).expanduser()
    return candidate if candidate.is_file() else None


def _resolve_remote_file(profile: ModelProfile) -> tuple[str, str]:
    api = HfApi()
    try:
        info = api.model_info(profile.repo_id, revision=profile.revision)
        revision = info.sha
        files = api.list_repo_files(profile.repo_id, revision=revision)
    except Exception as exc:
        raise ModelInstallError(f"Could not resolve {profile.repo_id}: {exc}") from exc

    matches = [
        name
        for name in files
        if fnmatch.fnmatch(Path(name).name, profile.filename_pattern)
        and "mmproj" not in Path(name).name.lower()
    ]
    if not matches:
        raise ModelInstallError(
            f"No GGUF in {profile.repo_id} matched {profile.filename_pattern!r}."
        )
    if len(matches) > 1:
        raise ModelInstallError(
            f"Model pattern matched multiple GGUFs in {profile.repo_id}: {matches[:8]}"
        )
    return matches[0], revision


def install_model(key: str, *, force: bool = False) -> dict:
    profile = get_model_profile(key)
    existing = installed_model_path(profile.key)
    if existing and not force:
        return model_status(profile.key)

    filename, revision = _resolve_remote_file(profile)
    model_dir = _cache_dir() / "models" / profile.key / revision[:12]
    model_dir.mkdir(parents=True, exist_ok=True)

    free = shutil.disk_usage(model_dir).free
    required = int((profile.approximate_size_gb + 2.0) * (1024 ** 3))
    if free < required:
        raise ModelInstallError(
            f"Not enough free disk space for {profile.display_name}. "
            f"Need about {profile.approximate_size_gb + 2.0:.1f} GiB with headroom; "
            f"only {free / (1024 ** 3):.1f} GiB is free."
        )

    try:
        downloaded = Path(
            hf_hub_download(
                repo_id=profile.repo_id,
                filename=filename,
                revision=revision,
                local_dir=model_dir,
            )
        ).resolve()
    except Exception as exc:
        raise ModelInstallError(f"Model download failed: {exc}") from exc

    if not downloaded.is_file():
        raise ModelInstallError("Download finished but the GGUF file is missing.")

    digest = _sha256(downloaded)
    if profile.expected_sha256 and digest.lower() != profile.expected_sha256.lower():
        downloaded.unlink(missing_ok=True)
        raise ModelInstallError(
            f"SHA-256 mismatch for {profile.key}. Expected {profile.expected_sha256}, got {digest}."
        )

    manifest = {
        "model_key": profile.key,
        "repo_id": profile.repo_id,
        "filename": filename,
        "revision": revision,
        "path": str(downloaded),
        "sha256": digest,
        "size_bytes": downloaded.stat().st_size,
    }
    _save_json(_manifest_path(profile.key), manifest)
    return model_status(profile.key)


def model_status(key: str) -> dict:
    profile = get_model_profile(key)
    path = installed_model_path(profile.key)
    manifest = _manifest(profile.key)
    return {
        "model": profile.key,
        "display_name": profile.display_name,
        "profile_status": profile.status,
        "selected": selected_model_key() == profile.key,
        "installed": bool(path),
        "path": str(path) if path else None,
        "repo_id": profile.repo_id,
        "revision": manifest.get("revision", profile.revision),
        "sha256": manifest.get("sha256"),
        "size_bytes": manifest.get("size_bytes", path.stat().st_size if path else None),
        "approximate_size_gb": profile.approximate_size_gb,
        "minimum_ram_gb": profile.minimum_ram_gb,
        "recommended_ram_gb": profile.recommended_ram_gb,
        "preferred_context": profile.preferred_context,
        "description": profile.description,
        "hardware_tier": profile.hardware_tier,
        "family": profile.family,
        "tool_call_quality": profile.tool_call_quality,
        "reasoning_strength": profile.reasoning_strength,
        "fim": profile.fim,
    }


def all_model_statuses() -> list[dict]:
    return [model_status(key) for key in MODEL_PROFILES]


def remove_model(key: str) -> bool:
    profile = get_model_profile(key)
    if os.environ.get("LOCDEX_MODEL_PATH") and profile.key == selected_model_key():
        raise ModelInstallError("Refusing to delete a model supplied through LOCDEX_MODEL_PATH.")

    manifest = _manifest(profile.key)
    if not manifest:
        return False

    path = Path(str(manifest.get("path", ""))).expanduser().resolve()
    models_root = (_cache_dir() / "models").resolve()
    if path.exists() and models_root in path.parents:
        shutil.rmtree(path.parent, ignore_errors=True)
    _manifest_path(profile.key).unlink(missing_ok=True)
    return True
