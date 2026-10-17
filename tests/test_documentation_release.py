"""Regression checks for Locdex v1.4 documentation and README Mermaid source.

These inspect a restricted diagram syntax subset and release naming. GitHub's
rendered output should still be reviewed separately.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

ARCHITECTURE_DOCS = [
    "README.md",
    "ARCHITECTURE.md",
    "BUILD_SPEC.md",
    "ROUTING_TELEMETRY.md",
    "SETUP_GUIDE.md",
    "START_HERE.md",
    "TESTING.md",
    "docs/V1_4_STABLE_ROADMAP.md",
]


@pytest.mark.parametrize("relative_path", ARCHITECTURE_DOCS)
def test_architecture_docs_use_v14_product_branding(relative_path: str) -> None:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    assert "v1.4" in source
    assert "v3.3" not in source
    assert "architecture-v3.2-ready" not in source


def test_release_status_is_unambiguous() -> None:
    source = (ROOT / "README.md").read_text(encoding="utf-8")
    notes = (ROOT / "docs/RELEASE_NOTES_V1_4_1.md").read_text(encoding="utf-8")
    assert "v1.3.1" in source
    assert "v1.4.0a1" in source
    assert "v1.4.1 (release-accepted)" in source
    assert "Actual published versions must be verified separately" in source
    assert "Local coding-agent release acceptance passed" in notes
    assert "4/4 passed" in notes
    assert "840.2 seconds" in notes


def test_readme_mermaid_uses_simple_flowchart_syntax() -> None:
    source = (ROOT / "README.md").read_text(encoding="utf-8")
    fence = chr(96) * 3
    diagrams = re.findall(
        rf"^{fence}mermaid[ \t]*\n(.*?)^{fence}[ \t]*$",
        source,
        flags=re.M | re.S,
    )
    assert len(diagrams) == 2, "Expected separate agent and runtime diagrams"

    # Avoid nested quoted shapes, inline punctuation, or complex edge syntax;
    # this is a static guard for common Mermaid failures, not a full parser.
    edge = re.compile(
        r"([A-Z][A-Z0-9_]*)"
        r"(?:\[([A-Za-z0-9 ]+)\])?"
        r" --> "
        r"([A-Z][A-Z0-9_]*)"
        r"(?:\[([A-Za-z0-9 ]+)\])?"
    )
    for diagram in diagrams:
        lines = [line.strip() for line in diagram.splitlines() if line.strip()]
        assert lines[0] == "flowchart TD"
        assert len(lines) >= 6
        defined: set[str] = set()
        references: set[str] = set()
        for line in lines[1:]:
            match = edge.fullmatch(line)
            assert match is not None, f"Unsupported Mermaid syntax: {line!r}"
            left, left_label, right, right_label = match.groups()
            references.update((left, right))
            if left_label:
                defined.add(left)
            if right_label:
                defined.add(right)
        assert references <= defined, "Diagram references an undefined node"


def test_architecture_readme_anchor_matches_section_title() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    anchor = "two-architectural-layers-one-v14-release"
    assert "## Two architectural layers, one v1.4 release" in readme
    assert f"(README.md#{anchor})" in architecture
