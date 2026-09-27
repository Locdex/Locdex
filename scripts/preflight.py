from __future__ import annotations

import argparse
import compileall
import importlib
import os
import pathlib
import pkgutil
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
SCRIPTS = ROOT / "scripts"

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".pytest-locdex",
    "dist",
    "build",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
}

TEXT_SUFFIXES = {".py", ".toml", ".md", ".yml", ".yaml", ".json"}


def run(
    cmd: list[str],
    *,
    cwd: pathlib.Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, check=False)
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


def _is_ignored(path: pathlib.Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def check_text_files() -> None:
    bad: list[str] = []
    conflict_markers = ("<<<<<<<", "=======", ">>>>>>>")

    files: set[pathlib.Path] = set()

    for base in (SRC, TESTS, SCRIPTS):
        if not base.exists():
            continue

        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if _is_ignored(path):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            files.add(path)

    for path in ROOT.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.add(path)

    for path in sorted(files):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            bad.append(f"{path.relative_to(ROOT)}: not UTF-8")
            continue

        lines = text.splitlines()
        if any(
            any(line.startswith(marker) for marker in conflict_markers)
            for line in lines
        ):
            bad.append(f"{path.relative_to(ROOT)}: merge-conflict marker present")

    if bad:
        raise SystemExit("FAIL:\n" + "\n".join(f"  - {item}" for item in bad))

    print("PASS: project text files are UTF-8 and contain no merge-conflict markers")


def check_no_cache_artifacts() -> None:
    offenders: list[str] = []

    for base in (SRC, TESTS, SCRIPTS):
        if not base.exists():
            continue

        for path in base.rglob("*"):
            if _is_ignored(path) and path.name not in {
                "__pycache__",
                ".pytest_cache",
                ".pytest-locdex",
            }:
                continue

            if (
                path.name in {"__pycache__", ".pytest_cache", ".pytest-locdex"}
                or path.suffix == ".pyc"
            ):
                offenders.append(str(path.relative_to(ROOT)))

    if offenders:
        print("WARN: generated cache artifacts exist; delete before commit:")
        for item in sorted(set(offenders))[:30]:
            print(f"  - {item}")
    else:
        print("PASS: no Python/pytest cache artifacts")


def compile_everything() -> None:
    targets = [path for path in (SRC, TESTS, SCRIPTS) if path.exists()]

    for target in targets:
        if not compileall.compile_dir(str(target), quiet=1, force=True):
            raise SystemExit(f"FAIL: Python compilation failed under {target}")

    print("PASS: every Python file under src/, tests/, and scripts/ compiles")


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

    failures: list[tuple[str, Exception]] = []

    for name in critical:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            failures.append((name, exc))

    if failures:
        msg = "\n".join(
            f"  - {name}: {type(exc).__name__}: {exc}"
            for name, exc in failures
        )
        raise SystemExit("FAIL: critical module import errors:\n" + msg)

    print(f"PASS: {len(critical)} critical modules import")

    if not strict:
        return

    locdex_pkg = importlib.import_module("locdex")

    failures = []
    count = 0

    for info in pkgutil.walk_packages(
        locdex_pkg.__path__,
        locdex_pkg.__name__ + ".",
    ):
        count += 1
        try:
            importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001
            failures.append((info.name, exc))

    if failures:
        msg = "\n".join(
            f"  - {name}: {type(exc).__name__}: {exc}"
            for name, exc in failures
        )
        raise SystemExit(
            "FAIL: one or more Locdex modules cannot import. "
            "Run this after `python -m pip install -e '.[dev]'`.\n"
            + msg
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

    run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(out),
        ]
    )

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

        missing = [
            suffix
            for suffix in required_suffixes
            if not any(name.endswith(suffix) for name in names)
        ]

        if missing:
            raise SystemExit(
                "FAIL: built wheel missing files: " + ", ".join(sorted(missing))
            )

        entry_points = [
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        ]

        if len(entry_points) != 1:
            raise SystemExit("FAIL: wheel is missing console entry-point metadata")

        entry_point_text = zf.read(entry_points[0]).decode("utf-8")
        if "locdex = locdex.main:cli" not in entry_point_text:
            raise SystemExit(
                "FAIL: wheel console entry point is not locdex.main:cli"
            )

    print(f"PASS: wheel built and inspected: {wheel.name}")
    return wheel


def wheel_smoke(wheel: pathlib.Path) -> None:
    temp = pathlib.Path(tempfile.mkdtemp(prefix="locdex-venv-"))

    try:
        # Use a genuinely clean environment. The release test must prove that
        # installing the wheel resolves Locdex's declared runtime dependencies.
        builder = venv.EnvBuilder(with_pip=True, system_site_packages=False)
        builder.create(temp)

        py = temp / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        exe = temp / ("Scripts/locdex.exe" if os.name == "nt" else "bin/locdex")

        # Install exactly as a normal user would. Missing dependencies in
        # pyproject.toml should fail this preflight instead of being hidden.
        run([str(py), "-m", "pip", "install", str(wheel)])

        # Validate the installed dependency graph before starting the CLI.
        run([str(py), "-m", "pip", "check"])
        run([str(exe), "--help"])

        print("PASS: built wheel installs with dependencies and the Locdex CLI starts")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Locdex preflight gate")
    parser.add_argument(
        "--strict-imports",
        action="store_true",
        help="Import every Locdex module. Run after installing all declared dependencies.",
    )
    parser.add_argument(
        "--skip-wheel",
        action="store_true",
        help="Skip wheel build/install smoke test",
    )
    args = parser.parse_args()

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
