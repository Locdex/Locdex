from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
from pathlib import Path

from .config import LocalModelConfig, load_local_model_config
from .model_profiles import MODEL_PROFILES


class ModelInstallError(RuntimeError):
    pass


def _manifest_path(config: LocalModelConfig) -> Path:
    return config.cache_dir / "manifests" / f"{config.model_key}.json"


def _sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(config: LocalModelConfig) -> dict | None:
    path = _manifest_path(config)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def installed_model_path(config: LocalModelConfig | None = None) -> Path | None:
    config = config or load_local_model_config()

    if config.explicit_model_path:
        return config.explicit_model_path if config.explicit_model_path.is_file() else None

    manifest = _read_manifest(config)
    if not manifest:
        return None

    candidate = Path(manifest.get("path", ""))
    return candidate if candidate.is_file() else None


def _resolve_remote_file(config: LocalModelConfig) -> tuple[str, str]:
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:  # pragma: no cover
        raise ModelInstallError("huggingface-hub is not installed. Reinstall Locdex.") from exc

    api = HfApi()
    try:
        info = api.model_info(config.repo_id, revision=config.revision)
        resolved_revision = info.sha
        files = api.list_repo_files(config.repo_id, revision=resolved_revision)
    except Exception as exc:
        raise ModelInstallError(f"Could not resolve model repository {config.repo_id}: {exc}") from exc

    matches = [
        name
        for name in files
        if fnmatch.fnmatch(Path(name).name, config.filename_pattern)
        and "mmproj" not in Path(name).name.lower()
    ]
    if not matches:
        raise ModelInstallError(f"No model file in {config.repo_id} matched {config.filename_pattern!r}.")
    if len(matches) > 1:
        exact_q4 = [name for name in matches if "q4_k_m" in name.lower()]
        if len(exact_q4) == 1:
            matches = exact_q4
        else:
            raise ModelInstallError(
                "Model pattern matched multiple files; set LOCDEX_MODEL_PATTERN to one GGUF file. "
                f"Matches: {matches[:8]}"
            )
    return matches[0], resolved_revision


def install_model(config: LocalModelConfig | None = None, force: bool = False) -> Path:
    config = config or load_local_model_config()

    if config.explicit_model_path:
        if not config.explicit_model_path.is_file():
            raise ModelInstallError(f"LOCDEX_MODEL_PATH does not exist: {config.explicit_model_path}")
        return config.explicit_model_path

    existing = installed_model_path(config)
    if existing and not force:
        return existing

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover
        raise ModelInstallError("huggingface-hub is not installed. Reinstall Locdex.") from exc

    filename, resolved_revision = _resolve_remote_file(config)
    model_dir = config.cache_dir / "models" / config.model_key / resolved_revision[:12]
    model_dir.mkdir(parents=True, exist_ok=True)

    free_bytes = shutil.disk_usage(model_dir).free
    required_bytes = int((config.profile.approximate_size_gb + 2.0) * (1024**3))
    if free_bytes < required_bytes:
        raise ModelInstallError(
            f"Not enough free disk space for {config.profile.display_name}. "
            f"Need roughly {config.profile.approximate_size_gb + 2.0:.1f} GiB including download/cache headroom; "
            f"only {free_bytes / (1024**3):.1f} GiB is free."
        )

    print(f"[Locdex model] Downloading {config.profile.display_name}...")
    try:
        downloaded = Path(
            hf_hub_download(
                repo_id=config.repo_id,
                filename=filename,
                revision=resolved_revision,
                local_dir=model_dir,
            )
        ).resolve()
    except Exception as exc:
        raise ModelInstallError(f"Model download failed: {exc}") from exc

    if not downloaded.is_file():
        raise ModelInstallError("Model download completed but the GGUF file could not be found.")

    print("[Locdex model] Verifying downloaded model...")
    digest = _sha256(downloaded)
    if config.expected_sha256 and digest.lower() != config.expected_sha256.strip().lower():
        downloaded.unlink(missing_ok=True)
        raise ModelInstallError(
            f"Downloaded {config.model_key} model SHA-256 did not match the Locdex-pinned digest."
        )

    manifest_path = _manifest_path(config)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_key": config.model_key,
        "repo_id": config.repo_id,
        "filename": filename,
        "revision": resolved_revision,
        "path": str(downloaded),
        "sha256": digest,
        "size_bytes": downloaded.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[Locdex model] Installed {config.model_key} at {downloaded}")
    return downloaded


def ensure_model(config: LocalModelConfig | None = None) -> Path:
    config = config or load_local_model_config()
    existing = installed_model_path(config)
    if existing:
        return existing
    if not config.auto_download:
        raise ModelInstallError(
            f"Model {config.model_key!r} is not installed and LOCDEX_AUTO_DOWNLOAD is disabled. "
            f"Run `locdex model install {config.model_key}`."
        )
    return install_model(config)


def model_status(config: LocalModelConfig | None = None) -> dict:
    config = config or load_local_model_config()
    path = installed_model_path(config)
    manifest = _read_manifest(config) or {}
    return {
        "model": config.model_key,
        "display_name": config.profile.display_name,
        "status": config.profile.status,
        "installed": bool(path),
        "path": str(path) if path else None,
        "repo_id": manifest.get("repo_id", config.repo_id),
        "revision": manifest.get("revision", config.revision),
        "sha256": manifest.get("sha256"),
        "size_bytes": manifest.get("size_bytes", path.stat().st_size if path else None),
        "pattern": config.filename_pattern,
    }


def all_model_statuses() -> list[dict]:
    return [model_status(load_local_model_config(key)) for key in MODEL_PROFILES]


def remove_model(config: LocalModelConfig | None = None) -> bool:
    config = config or load_local_model_config()
    if config.explicit_model_path:
        raise ModelInstallError("Refusing to delete a model supplied through LOCDEX_MODEL_PATH.")

    manifest = _read_manifest(config)
    if not manifest:
        return False

    path = Path(manifest.get("path", ""))
    models_root = config.cache_dir / "models"
    if path.exists() and models_root in path.parents:
        revision_dir = path.parent
        shutil.rmtree(revision_dir, ignore_errors=True)
    _manifest_path(config).unlink(missing_ok=True)
    return True
