from __future__ import annotations

import argparse
import compileall
import importlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"


def run(cmd: list[str], *, cwd: pathlib.Path = ROOT, env: dict[str, str] | None = None) -> None:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True)
    if proc.returncode:
        raise SystemExit(proc.returncode)


def check_pyproject() -> None:
    path = ROOT / "pyproject.toml"
    if not path.exists():
        raise SystemExit("FAIL: pyproject.toml not found")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    if project.get("name") != "locdex":
        raise SystemExit("FAIL: [project].name must be 'locdex'")
    scripts = project.get("scripts", {})
    if scripts.get("locdex") != "locdex.main:cli":
        raise SystemExit("FAIL: locdex console script must point to locdex.main:cli")
    print("PASS: pyproject.toml")


def check_text_files() -> None:
    bad = []
    conflict_markers = ("<<<<<<<", "=======", ">>>>>>>")
    for base in (ROOT, SRC, TESTS):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or any(part in {".git", "__pycache__", ".pytest_cache", "dist", "build"} for part in p.parts):
                continue
            if p.suffix.lower() not in {".py", ".toml", ".md", ".yml", ".yaml", ".json"}:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                bad.append(f"{p.relative_to(ROOT)}: not UTF-8")
                continue
            lines = text.splitlines()
            if any(any(line.startswith(marker) for marker in conflict_markers) for line in lines):
                bad.append(f"{p.relative_to(ROOT)}: merge-conflict marker present")
    if bad:
        raise SystemExit("FAIL:\n" + "\n".join(f"  - {x}" for x in bad))
    print("PASS: text files are UTF-8 and contain no merge-conflict markers")


def check_no_cache_artifacts() -> None:
    offenders = []
    for p in ROOT.rglob("*"):
        if any(part == ".git" for part in p.parts):
            continue
        if p.name in {"__pycache__", ".pytest_cache"} or p.suffix == ".pyc":
            offenders.append(str(p.relative_to(ROOT)))
    if offenders:
        print("WARN: generated cache artifacts exist; delete before commit:")
        for item in offenders[:30]:
            print(f"  - {item}")
    else:
        print("PASS: no Python/pytest cache artifacts")


def compile_everything() -> None:
    targets = [p for p in (SRC, TESTS) if p.exists()]
    for target in targets:
        if not compileall.compile_dir(str(target), quiet=1, force=True):
            raise SystemExit(f"FAIL: Python compilation failed under {target}")
    print("PASS: every Python file under src/ and tests/ compiles")


def import_modules(strict: bool) -> None:
    sys.path.insert(0, str(SRC))
    critical = [
        "locdex.main",
        "locdex.agent",
        "locdex.agent_tools",
        "locdex.router",
        "locdex.local_runtime",
        "locdex.runtime_manager",
        "locdex.model_manager",
        "locdex.cloud_fallback",
        "locdex.telemetry",
        "locdex.validator",
    ]
    failures = []
    for name in critical:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            failures.append((name, exc))
    if failures:
        msg = "\n".join(f"  - {name}: {type(exc).__name__}: {exc}" for name, exc in failures)
        raise SystemExit("FAIL: critical module import errors:\n" + msg)
    print(f"PASS: {len(critical)} critical modules import")

    if not strict:
        return
    import pkgutil
    import locdex

    failures = []
    count = 0
    for info in pkgutil.walk_packages(locdex.__path__, locdex.__name__ + "."):
        count += 1
        try:
            importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001
            failures.append((info.name, exc))
    if failures:
        msg = "\n".join(f"  - {name}: {type(exc).__name__}: {exc}" for name, exc in failures)
        raise SystemExit(
            "FAIL: one or more Locdex modules cannot import. "
            "Run this after `python -m pip install -e '.[dev]'`.\n" + msg
        )
    print(f"PASS: all {count} discoverable Locdex modules import")


def pytest_gate() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    run([sys.executable, "-m", "pytest", "--collect-only", "-q"], env=env)
    run([sys.executable, "-m", "pytest", "-q"], env=env)
    print("PASS: pytest collection and regression suite")


def build_wheel() -> pathlib.Path:
    out = pathlib.Path(tempfile.mkdtemp(prefix="locdex-wheel-"))
    run([
        sys.executable,
        "-m",
        "pip",
        "wheel",
        ".",
        "--no-deps",
        "--no-build-isolation",
        "-w",
        str(out),
    ])
    wheels = sorted(out.glob("locdex-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"FAIL: expected one Locdex wheel, found {len(wheels)}")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        required_suffixes = {
            "locdex/main.py",
            "locdex/agent.py",
            "locdex/router.py",
            "locdex/telemetry.py",
        }
        missing = [s for s in required_suffixes if not any(n.endswith(s) for n in names)]
        if missing:
            raise SystemExit("FAIL: built wheel missing files: " + ", ".join(missing))
        entry_points = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
        if len(entry_points) != 1:
            raise SystemExit("FAIL: wheel is missing console entry-point metadata")
        ep = zf.read(entry_points[0]).decode("utf-8")
        if "locdex = locdex.main:cli" not in ep:
            raise SystemExit("FAIL: wheel console entry point is not locdex.main:cli")
    print(f"PASS: wheel built and inspected: {wheel.name}")
    return wheel


def wheel_smoke(wheel: pathlib.Path) -> None:
    temp = pathlib.Path(tempfile.mkdtemp(prefix="locdex-venv-"))
    builder = venv.EnvBuilder(with_pip=True, system_site_packages=True)
    builder.create(temp)
    py = temp / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    exe = temp / ("Scripts/locdex.exe" if os.name == "nt" else "bin/locdex")
    run([str(py), "-m", "pip", "install", "--no-deps", str(wheel)])
    run([str(exe), "--help"])
    print("PASS: built wheel installs and the Locdex CLI starts")
    shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Locdex preflight gate")
    ap.add_argument(
        "--strict-imports",
        action="store_true",
        help="Import every Locdex module. Run after installing all declared dependencies.",
    )
    ap.add_argument("--skip-wheel", action="store_true", help="Skip wheel build/install smoke test")
    args = ap.parse_args()

    print("=== Locdex preflight ===")
    check_pyproject()
    check_text_files()
    check_no_cache_artifacts()
    compile_everything()
    import_modules(args.strict_imports)
    pytest_gate()
    if not args.skip_wheel:
        wheel = build_wheel()
        wheel_smoke(wheel)
    print("\nALL PREFLIGHT CHECKS PASSED")


if __name__ == "__main__":
    main()
