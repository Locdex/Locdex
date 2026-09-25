from __future__ import annotations

from locdex import runtime_manager


def _profile(**overrides):
    values = {
        "system": "Windows",
        "machine": "amd64",
        "python": "3.11",
        "backend": "cpu",
        "accelerator": None,
        "vram_gb": None,
        "system_ram_gb": 8.0,
        "cuda_version": None,
        "wheel_index": "https://example.invalid/cpu",
        "auto_gpu_layers": 0,
    }
    values.update(overrides)
    return runtime_manager.HardwareProfile(**values)


def test_nearest_cuda_wheel_selects_supported_floor():
    assert runtime_manager._nearest_cuda_wheel("12.6") == "cu125"
    assert runtime_manager._nearest_cuda_wheel("12.4") == "cu124"
    assert runtime_manager._nearest_cuda_wheel("11.7") is None


def test_cpu_detection_when_no_accelerator(monkeypatch):
    monkeypatch.setattr(runtime_manager.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime_manager.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(runtime_manager.shutil, "which", lambda name: None)
    monkeypatch.setattr(runtime_manager, "_system_ram_gb", lambda: 16.0)
    profile = runtime_manager.detect_hardware()
    assert profile.backend == "cpu"
    assert profile.auto_gpu_layers == 0
    assert profile.wheel_index.endswith("/cpu")


def test_nvidia_detection_prefers_cuda_prebuilt(monkeypatch):
    monkeypatch.setattr(runtime_manager.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime_manager.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(runtime_manager, "_system_ram_gb", lambda: 32.0)
    monkeypatch.setattr(
        runtime_manager.shutil,
        "which",
        lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None,
    )
    monkeypatch.setattr(
        runtime_manager,
        "_nvidia_profile",
        lambda: ("NVIDIA RTX Test", 12.0, "12.4"),
    )
    profile = runtime_manager.detect_hardware()
    if runtime_manager.sys.version_info[:2] in {(3, 10), (3, 11), (3, 12)}:
        assert profile.backend == "cuda"
        assert profile.wheel_index.endswith("/cu124")
    else:
        assert profile.backend == "cpu"


def test_runtime_installer_never_builds_from_source(monkeypatch):
    profile = _profile(system="Linux", machine="x86_64")
    monkeypatch.setattr(runtime_manager, "effective_hardware_profile", lambda refresh=False: profile)
    monkeypatch.setattr(runtime_manager, "_read_install_marker", lambda: None)
    monkeypatch.setattr(runtime_manager, "cache_hardware_profile", lambda profile: None)
    monkeypatch.setattr(runtime_manager, "_write_install_marker", lambda profile, source="locdex": None)

    captured = []

    class Result:
        returncode = 0

    def fake_run(command, check=False):
        captured.append(command)
        return Result()

    versions = iter([None, "0.3.35"])
    monkeypatch.setattr(runtime_manager, "installed_runtime_version", lambda: next(versions))
    monkeypatch.setattr(runtime_manager.subprocess, "run", fake_run)

    runtime_manager.install_runtime(force=True)

    assert "--only-binary=:all:" in captured[0]
    assert "--extra-index-url" in captured[0]


def test_windows_cpu_falls_back_to_official_github_release(monkeypatch):
    profile = _profile()
    monkeypatch.setattr(runtime_manager, "effective_hardware_profile", lambda refresh=False: profile)
    monkeypatch.setattr(runtime_manager, "_read_install_marker", lambda: None)
    monkeypatch.setattr(runtime_manager, "cache_hardware_profile", lambda profile: None)

    marker = {}
    monkeypatch.setattr(
        runtime_manager,
        "_write_install_marker",
        lambda profile, source="locdex": marker.update(source=source, backend=profile.backend),
    )

    commands = []

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    results = iter([Result(1), Result(0)])

    def fake_run(command, check=False):
        commands.append(command)
        return next(results)

    versions = iter([None, "0.3.35"])
    monkeypatch.setattr(runtime_manager, "installed_runtime_version", lambda: next(versions))
    monkeypatch.setattr(runtime_manager.subprocess, "run", fake_run)

    runtime_manager.install_runtime(force=True)

    assert len(commands) == 2
    assert "--extra-index-url" in commands[0]
    assert commands[1][-1].endswith(
        "/v0.3.35/llama_cpp_python-0.3.35-py3-none-win_amd64.whl"
    )
    assert marker == {"source": "official-github-release", "backend": "cpu"}


def test_markerless_cpu_install_is_adopted_without_redownload(monkeypatch):
    profile = _profile()
    monkeypatch.setattr(runtime_manager, "effective_hardware_profile", lambda refresh=False: profile)
    monkeypatch.setattr(runtime_manager, "_read_install_marker", lambda: None)
    monkeypatch.setattr(runtime_manager, "installed_runtime_version", lambda: "0.3.35")
    monkeypatch.setattr(runtime_manager, "cache_hardware_profile", lambda profile: None)

    marker = {}
    monkeypatch.setattr(
        runtime_manager,
        "_write_install_marker",
        lambda profile, source="locdex": marker.update(source=source, backend=profile.backend),
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("pip should not run for an adopted manual CPU install")

    monkeypatch.setattr(runtime_manager.subprocess, "run", should_not_run)

    runtime_manager.install_runtime(force=False)
    assert marker == {"source": "adopted-manual-install", "backend": "cpu"}


def test_runtime_status_infers_markerless_cpu_backend(monkeypatch):
    profile = _profile()
    monkeypatch.setattr(runtime_manager, "effective_hardware_profile", lambda refresh=False: profile)
    monkeypatch.setattr(runtime_manager, "_read_install_marker", lambda: None)
    monkeypatch.setattr(runtime_manager, "installed_runtime_version", lambda: "0.3.35")

    status = runtime_manager.runtime_status()
    assert status["installed"] is True
    assert status["installed_backend"] == "cpu"
