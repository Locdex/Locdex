from __future__ import annotations

from locdex.runtime.hardware import HardwareProfile, _parse_nvidia_query
from locdex.runtime.installer import build_install_command, plan_runtime_install, select_cuda_track


def test_parse_nvidia_query():
    rows = _parse_nvidia_query("NVIDIA GeForce RTX 4060, 8192, 7000, 576.40\n")
    assert rows == [
        {
            "name": "NVIDIA GeForce RTX 4060",
            "vram_total_gb": 8.0,
            "vram_free_gb": 6.84,
            "driver_version": "576.40",
        }
    ]


def test_cuda_track_uses_nearest_supported_not_newer():
    assert select_cuda_track("12.8") == "cu125"
    assert select_cuda_track("13.1") == "cu130"
    assert select_cuda_track("13.2") == "cu132"
    assert select_cuda_track("11.7") is None


def test_cuda_install_plan(monkeypatch):
    import locdex.runtime.installer as installer

    monkeypatch.setattr(installer, "_python_version_tuple", lambda: (3, 11))
    hardware = HardwareProfile(
        "Windows",
        "AMD64",
        8,
        31.7,
        20.0,
        "cuda",
        cpu_name="Example CPU",
        physical_cpu_count=4,
        accelerator="nvidia",
        gpu_name="Example RTX",
        vram_total_gb=8.0,
        vram_free_gb=7.0,
        cuda_version="12.8",
        driver_version="576.40",
    )
    plan = plan_runtime_install(hardware)
    assert plan.backend == "cuda"
    assert plan.cuda_track == "cu125"
    assert plan.index_url.endswith("/cu125")


def test_runtime_install_never_builds_llama_cpp_from_source(monkeypatch):
    import locdex.runtime.installer as installer

    monkeypatch.setattr(installer, "_python_version_tuple", lambda: (3, 11))
    hardware = HardwareProfile("Windows", "AMD64", 8, 16.0, 10.0, "cpu")
    plan = plan_runtime_install(hardware)
    command = build_install_command(plan)
    assert "--only-binary=llama-cpp-python" in command
    assert "--prefer-binary" in command
    assert "--extra-index-url" in command
    assert plan.index_url.endswith("/cpu")
