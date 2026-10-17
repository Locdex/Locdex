"""Distribution version alignment: PyPI package, CLI and npm wrapper."""
from __future__ import annotations

import json
import re
from pathlib import Path

import locdex


ROOT = Path(__file__).resolve().parents[1]


def test_release_candidate_versions_match_across_artifacts():
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', metadata)
    assert match is not None
    python_version = match.group(1)

    npm = json.loads((ROOT / "npm/locdex-cli/package.json").read_text(encoding="utf-8"))
    installer = (ROOT / "npm/locdex-cli/scripts/install.js").read_text(encoding="utf-8")

    assert python_version == "1.4.1"
    assert locdex.__version__ == python_version
    assert npm["version"] == python_version
    assert f"locdex=={python_version}" in installer
