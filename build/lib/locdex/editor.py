from __future__ import annotations

import ast
import os

IGNORE_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", "env", ".pytest_cache"}
MAX_CONTEXT_LENGTH = 15000


def extract_skeleton(filepath: str) -> str:
    """Return a compact structural skeleton for a Python source file."""
    try:
        with open(filepath, "r", encoding="utf-8") as handle:
            content = handle.read()
        tree = ast.parse(content)
        skeleton: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = ", ".join(arg.arg for arg in node.args.args)
                skeleton.append(f"def {node.name}({args}): ...")
            elif isinstance(node, ast.ClassDef):
                skeleton.append(f"class {node.name}:")
                methods = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if not methods:
                    skeleton.append("    pass")
                for item in methods:
                    args = ", ".join(arg.arg for arg in item.args.args)
                    skeleton.append(f"    def {item.name}({args}): ...")
        if skeleton:
            return "\n".join(skeleton)
        return content[:200] + "\n... (raw script omitted)"
    except SyntaxError:
        return "<SyntaxError: unparseable file>"
    except OSError as exc:
        return f"<Error reading file: {exc}>"


def get_workspace_context(repo_path: str) -> str:
    """Build a compact architectural map without sending whole source files."""
    context: list[str] = []
    char_count = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(root, filename)
            skeleton = extract_skeleton(filepath)
            file_context = f"\n--- {filepath} (Architecture Skeleton) ---\n{skeleton}\n"
            if char_count + len(file_context) > MAX_CONTEXT_LENGTH:
                context.append("\n[Warning: Workspace map truncated due to size limits]")
                return "".join(context)
            context.append(file_context)
            char_count += len(file_context)
    return "".join(context)
