from __future__ import annotations

import compileall
import importlib
import pkgutil
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
PREFLIGHT_TMP = ROOT / ".preflight-tmp"
PYTEST_TMP = ROOT / ".pytest-tmp"


def run(args: list[str], *, with_src: bool = False) -> None:
    print("$", " ".join(str(x) for x in args))
    env = None
    if with_src:
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(args, cwd=ROOT, check=True, env=env)


def _prepare_local_temp() -> None:
    shutil.rmtree(PREFLIGHT_TMP, ignore_errors=True)
    shutil.rmtree(PYTEST_TMP, ignore_errors=True)
    PREFLIGHT_TMP.mkdir(parents=True, exist_ok=True)


def main() -> int:
    _prepare_local_temp()

    if not compileall.compile_dir(str(SRC), quiet=1, force=True):
        raise SystemExit("source compilation failed")
    if not compileall.compile_dir(str(TESTS), quiet=1, force=True):
        raise SystemExit("test compilation failed")
    print("PASS compileall")

    sys.path.insert(0, str(SRC))
    import locdex
    count = 0
    for mod in pkgutil.walk_packages(locdex.__path__, "locdex."):
        importlib.import_module(mod.name)
        count += 1
    print(f"PASS strict imports ({count} modules)")

    pytest_base = str(PYTEST_TMP)
    run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--basetemp", pytest_base],
        with_src=True,
    )
    run(
        [sys.executable, "-m", "pytest", "-q", "--basetemp", pytest_base],
        with_src=True,
    )

    with tempfile.TemporaryDirectory(prefix="wheel-", dir=PREFLIGHT_TMP) as td:
        out = Path(td)
        run([
            sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
            "--no-build-isolation", "-w", str(out),
        ])
        wheels = list(out.glob("locdex-*.whl"))
        if len(wheels) != 1:
            raise SystemExit("expected exactly one wheel")
        wheel = wheels[0]

        with zipfile.ZipFile(wheel) as zf:
            names = set(zf.namelist())

        required = {
            "locdex/cli/app.py",
            "locdex/agent/engine.py",
            "locdex/agent/protocol.py",
            "locdex/context/compiler.py",
            "locdex/models/manager.py",
            "locdex/models/profiles.py",
            "locdex/security/policy.py",
            "locdex/routing/planner.py",
            "locdex/routing/router.py",
            "locdex/routing/task_profile.py",
            "locdex/runtime/hardware.py",
            "locdex/runtime/installer.py",
            "locdex/runtime/llama_cpp.py",
            "locdex/runtime/manager.py",
            "locdex/telemetry/schema.py",
            "locdex/telemetry/client.py",
            "locdex/tools/executor.py",
            "locdex/tools/registry.py",
            "locdex/extensions/enterprise.py",
        }
        missing = required - names
        if missing:
            raise SystemExit(f"wheel missing: {sorted(missing)}")

        with tempfile.TemporaryDirectory(prefix="venv-", dir=PREFLIGHT_TMP) as vd:
            env = Path(vd) / "venv"
            venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env)
            py = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            exe = env / ("Scripts/locdex.exe" if sys.platform == "win32" else "bin/locdex")
            run([str(py), "-m", "pip", "install", "--force-reinstall", "--no-deps", str(wheel)])
            run([str(exe), "--help"])

    print("ALL PREFLIGHT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
