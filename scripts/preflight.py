from __future__ import annotations

import compileall
import importlib
import pkgutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"


def run(args: list[str], *, with_src: bool = False) -> None:
    print("$", " ".join(args))
    env = None
    if with_src:
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(args, cwd=ROOT, check=True, env=env)


def main() -> int:
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

    run([sys.executable, "-m", "pytest", "--collect-only", "-q"], with_src=True)
    run([sys.executable, "-m", "pytest", "-q"], with_src=True)

    with tempfile.TemporaryDirectory(prefix="locdex-wheel-") as td:
        out = Path(td)
        run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "-w", str(out)])
        wheels = list(out.glob("locdex-*.whl"))
        if len(wheels) != 1:
            raise SystemExit("expected exactly one wheel")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as zf:
            names = set(zf.namelist())
        required = {
            "locdex/cli/app.py",
            "locdex/agent/engine.py",
            "locdex/context/compiler.py",
            "locdex/security/policy.py",
            "locdex/routing/planner.py",
            "locdex/routing/router.py",
            "locdex/routing/task_profile.py",
            "locdex/telemetry/schema.py",
            "locdex/telemetry/client.py",
            "locdex/extensions/enterprise.py",
        }
        missing = required - names
        if missing:
            raise SystemExit(f"wheel missing: {sorted(missing)}")

        with tempfile.TemporaryDirectory(prefix="locdex-venv-") as vd:
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
