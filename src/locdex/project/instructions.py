from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_INSTRUCTION_CHARS = 40_000
MAX_SKILLS = 20
MAX_SKILL_CHARS = 12_000


@dataclass(frozen=True)
class ProjectInstructions:
    files: tuple[str, ...]
    content: str
    skills: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "content": self.content,
            "skills": [dict(row) for row in self.skills],
        }


def _safe_root(repo_path: str) -> Path:
    root = Path(repo_path).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository path does not exist: {root}")
    return root


def _read_text(path: Path, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except (OSError, UnicodeDecodeError):
        return ""


def discover_project_instructions(repo_path: str) -> ProjectInstructions:
    root = _safe_root(repo_path)
    candidates = (
        root / "AGENTS.md",
        root / "LOCDEX.md",
        root / ".locdex" / "instructions.md",
    )

    files: list[str] = []
    sections: list[str] = []
    used = 0

    for path in candidates:
        if not path.is_file():
            continue
        remaining = MAX_INSTRUCTION_CHARS - used
        if remaining <= 0:
            break
        text = _read_text(path, remaining)
        if not text.strip():
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        files.append(relative)
        sections.append(f"### {relative}\n{text.strip()}")
        used += len(text)

    skills: list[dict[str, str]] = []
    skill_dir = root / ".locdex" / "skills"
    if skill_dir.is_dir():
        for path in sorted(skill_dir.glob("*.md"))[:MAX_SKILLS]:
            text = _read_text(path, MAX_SKILL_CHARS)
            if not text.strip():
                continue
            skills.append(
                {
                    "name": path.stem,
                    "path": str(path.relative_to(root)).replace("\\", "/"),
                    "content": text.strip(),
                }
            )

    return ProjectInstructions(
        files=tuple(files),
        content="\n\n".join(sections),
        skills=tuple(skills),
    )


def project_instruction_prompt(repo_path: str) -> str:
    discovered = discover_project_instructions(repo_path)
    chunks: list[str] = []

    if discovered.content:
        chunks.append(
            "PROJECT INSTRUCTIONS\n"
            "These repository instructions are user/project policy. Follow them unless "
            "they conflict with higher-priority Locdex safety policy.\n\n"
            + discovered.content
        )

    if discovered.skills:
        rows = []
        for skill in discovered.skills:
            rows.append(
                f"### Skill: {skill['name']} ({skill['path']})\n{skill['content']}"
            )
        chunks.append(
            "LOCAL PROJECT SKILLS\n"
            "Use these project-provided workflows when relevant to the user's task.\n\n"
            + "\n\n".join(rows)
        )

    return "\n\n".join(chunks)
