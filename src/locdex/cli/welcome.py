"""Compact, terminal-aware Locdex interactive welcome panel."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .. import __version__

_LOGO = (
    r" _     ___   ____ ____  _____ __  __",
    r"| |   / _ \ / ___|  _ \| ____|\ \/ /",
    r"| |  | | | | |   | | | |  _|   \  / ",
    r"| |__| |_| | |___| |_| | |___  /  \ ",
    r"|_____\___/ \____|____/|_____|/_/\_\\",
)


def welcome_panel(
    *,
    repo_path: str,
    model: str,
    permission_mode: str,
    sandbox_mode: str,
    columns: int | None = None,
    color: bool = False,
) -> str:
    """Return a readable panel without escaping/control codes in plain mode."""
    cols = columns if columns is not None else shutil.get_terminal_size((88, 24)).columns
    wide = cols >= 76
    repo = Path(repo_path).name or str(repo_path)
    rows = [
        "Local-first coding agent · repository intelligence + verified changes",
        f"Workspace  {repo}",
        f"Model      {model}",
        f"Security   {permission_mode} permissions · {sandbox_mode} sandbox",
        "Commands   /help  ·  /status  ·  /model  ·  exit",
    ]
    if wide:
        body = ["  " + line for line in _LOGO] + ["", f"  Welcome to Locdex v{__version__}", ""]
    else:
        body = [f"Locdex v{__version__}", ""]
        rows[0] = "Local-first coding agent"
    body.extend(rows)
    width = min(max(len(line) for line in body) + 4, max(cols, 24))
    if cols < 40:
        # Narrow terminals: no clipped borders or horizontal scrolling.
        body = [f"Locdex v{__version__}", f"Model: {model}", "/help · /status · exit"]
        return "\n".join(body)
    top = "╭" + "─" * (width - 2) + "╮"
    bottom = "╰" + "─" * (width - 2) + "╯"
    lines = [top]
    for line in body:
        lines.append("│ " + line[: width - 4].ljust(width - 4) + " │")
    lines.append(bottom)
    output = "\n".join(lines)
    if color:
        # Apply color only to the known, fixed branding; never interpolate
        # uncontrolled repository strings into ANSI control sequences.
        output = "\033[36m" + output + "\033[0m"
    return output


def print_welcome(*, repo_path: str, model: str, permission_mode: str, sandbox_mode: str) -> None:
    color = (
        sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM", "") != "dumb"
    )
    print()
    print(welcome_panel(
        repo_path=repo_path,
        model=model,
        permission_mode=permission_mode,
        sandbox_mode=sandbox_mode,
        color=color,
    ))
    print()
