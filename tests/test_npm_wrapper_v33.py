from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NPM = ROOT / "npm" / "locdex-cli"


def test_npm_package_metadata():
    package = json.loads((NPM / "package.json").read_text(encoding="utf-8"))

    assert package["name"] == "@locdex/cli"
    assert package["version"] == "1.4.1"
    assert package["bin"]["locdex"] == "bin/locdex.js"
    assert package["scripts"]["postinstall"] == "node scripts/install.js"
    assert package["engines"]["node"] == ">=18"
    assert package["publishConfig"]["access"] == "public"
    assert package["repository"]["directory"] == "npm/locdex-cli"
    assert {"bin", "scripts", "README.md"} <= set(package["files"])


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_npm_javascript_has_valid_syntax():
    for relative in (
        "bin/locdex.js",
        "scripts/runtime.js",
        "scripts/install.js",
    ):
        subprocess.run(
            ["node", "--check", str(NPM / relative)],
            cwd=NPM,
            check=True,
            capture_output=True,
            text=True,
        )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_npm_bootstrap_can_be_skipped_without_side_effects(tmp_path):
    env = os.environ.copy()
    env["LOCDEX_NPM_SKIP_BOOTSTRAP"] = "1"
    env["LOCDEX_NPM_RUNTIME_DIR"] = str(tmp_path / "runtime")

    process = subprocess.run(
        ["node", str(NPM / "scripts" / "install.js")],
        cwd=NPM,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0
    assert "Skipping Python bootstrap" in process.stdout
    assert not (tmp_path / "runtime").exists()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_npm_launcher_fails_cleanly_when_runtime_missing(tmp_path):
    env = os.environ.copy()
    env["LOCDEX_NPM_RUNTIME_DIR"] = str(tmp_path / "missing-runtime")

    process = subprocess.run(
        ["node", str(NPM / "bin" / "locdex.js"), "--version"],
        cwd=NPM,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 1
    assert "Managed Python runtime is missing" in process.stderr


@pytest.mark.skipif(shutil.which("npm") is None, reason="npm is not installed")
def test_npm_package_can_be_dry_run_packed():
    npm = shutil.which("npm")
    assert npm is not None

    npm_args = ["pack", "--dry-run", "--ignore-scripts"]
    if os.name == "nt":
        comspec = os.environ.get("ComSpec") or "cmd.exe"
        command = [
            comspec,
            "/d",
            "/c",
            "call",
            npm,
            *npm_args,
        ]
    else:
        command = [npm, *npm_args]

    process = subprocess.run(
        command,
        cwd=NPM,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert process.returncode == 0, process.stderr

    # npm's --json output shape varies across npm/platform versions. The
    # human-readable dry-run output is the stable contract we need here:
    # verify the package succeeds and includes the files we intend to ship.
    output = (process.stdout + "\n" + process.stderr).replace("\\", "/")
    assert "bin/locdex.js" in output
    assert "scripts/install.js" in output
    assert "scripts/runtime.js" in output
    assert "README.md" in output



def test_npm_python_version_pin_matches_project_metadata():
    import re
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    installer = (NPM / "scripts" / "install.js").read_text(encoding="utf-8")
    package = json.loads((NPM / "package.json").read_text(encoding="utf-8"))
    project_version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', project)
    assert project_version is not None
    assert f'locdex=={project_version.group(1)}' in installer
    prerelease = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)-alpha\.(\d+)", package["version"])
    if prerelease:
        expected_python = f"{prerelease[1]}.{prerelease[2]}.{prerelease[3]}a{prerelease[4]}"
    else:
        assert re.fullmatch(r"\d+\.\d+\.\d+", package["version"])
        expected_python = package["version"]
    assert project_version.group(1) == expected_python


def test_npm_readme_is_public_product_documentation():
    readme = (NPM / "README.md").read_text(encoding="utf-8")
    assert "npm install -g @locdex/cli" in readme
    assert "locdex runtime install --backend auto" in readme
    assert "locdex model list" in readme
    for internal_instruction in (
        "Package release verification",
        "Registry release checklist",
        "npm publish",
        "npm whoami",
        "publish the prerelease",
        "Do not publish from a checkout",
    ):
        assert internal_instruction not in readme
