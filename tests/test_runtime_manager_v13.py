from __future__ import annotations

from src.locdex import runtime_manager


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
    monkeypatch.setattr(runtime_manager.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
    monkeypatch.setattr(
        runtime_manager,
        "_nvidia_profile",
        lambda: ("NVIDIA RTX Test", 12.0, "12.4"),
    )
    profile = runtime_manager.detect_hardware()
    # Accelerated prebuilt wheels are deliberately limited to Python 3.10-3.12 by upstream.
    if runtime_manager.sys.version_info[:2] in {(3, 10), (3, 11), (3, 12)}:
        assert profile.backend == "cuda"
        assert profile.wheel_index.endswith("/cu124")
    else:
        assert profile.backend == "cpu"


def test_runtime_installer_never_builds_from_source(monkeypatch, tmp_path):
    profile = runtime_manager.HardwareProfile(
        system="Linux",
        machine="x86_64",
        python="3.12",
        backend="cpu",
        accelerator=None,
        vram_gb=None,
        system_ram_gb=16.0,
        cuda_version=None,
        wheel_index="https://example.invalid/cpu",
        auto_gpu_layers=0,
    )
    monkeypatch.setattr(runtime_manager, "effective_hardware_profile", lambda refresh=False: profile)
    monkeypatch.setattr(runtime_manager, "installed_runtime_version", lambda: None)
    monkeypatch.setattr(runtime_manager, "cache_hardware_profile", lambda profile: None)
    monkeypatch.setattr(runtime_manager, "_write_install_marker", lambda profile: None)
    captured = {}

    class Result:
        returncode = 0

    def fake_run(command, check=False):
        captured["command"] = command
        return Result()

    versions = iter([None, "0.3.35"])
    monkeypatch.setattr(runtime_manager, "installed_runtime_version", lambda: next(versions))
    monkeypatch.setattr(runtime_manager.subprocess, "run", fake_run)
    runtime_manager.install_runtime(force=True)
    assert "--only-binary=:all:" in captured["command"]
    assert "--extra-index-url" in captured["command"]
