from __future__ import annotations

import subprocess

import locdex.runtime.hardware as hardware_module


def test_windows_hardware_uses_native_ram_cpu_and_nvidia(monkeypatch):
    monkeypatch.setattr(hardware_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(hardware_module.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(hardware_module.platform, "processor", lambda: "")
    monkeypatch.setattr(hardware_module.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(hardware_module, "_windows_memory", lambda: (31.72, 22.10))
    monkeypatch.setattr(hardware_module, "_windows_cpu", lambda: ("AMD Ryzen Test", 8, 16))
    monkeypatch.setattr(
        hardware_module,
        "_detect_nvidia",
        lambda: {
            "name": "NVIDIA GeForce RTX Test",
            "vram_total_gb": 8.0,
            "vram_free_gb": 7.2,
            "cuda_version": "12.8",
            "driver_version": "576.40",
        },
    )

    profile = hardware_module.detect_hardware()
    assert profile.system == "Windows"
    assert profile.cpu_name == "AMD Ryzen Test"
    assert profile.physical_cpu_count == 8
    assert profile.cpu_count == 16
    assert profile.total_ram_gb == 31.72
    assert profile.available_ram_gb == 22.10
    assert profile.accelerator == "nvidia"
    assert profile.backend == "cuda"
    assert profile.vram_total_gb == 8.0
    assert profile.cuda_version == "12.8"


def test_external_hardware_probe_timeout_is_nonfatal(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(hardware_module.subprocess, "run", timeout)
    assert hardware_module._run_text(["fake-probe"], timeout=0.01) == ""
