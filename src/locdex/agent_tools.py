from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

IGNORED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
TEXT_EXTENSIONS = {".py", ".pyi", ".toml", ".md", ".txt", ".json", ".yaml", ".yml", ".ini", ".cfg", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".hpp", ".sh", ".sql", ".css", ".scss", ".html", ".vue", ".svelte", ".xml", ".gradle", ".properties"}
MAX_READ_BYTES = 2_000_000
MAX_TOOL_OUTPUT = 20_000
MAX_COMMAND_SECONDS = 180
BLOCKED_EXECUTABLES = {"sudo", "su", "doas", "shutdown", "reboot", "halt", "poweroff", "git", "gh"}
SECRET_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "PRIVATE_KEY", "CREDENTIAL")

class ToolError(ValueError):
    pass

def _root(repo_path: str) -> Path:
    root = Path(repo_path).resolve()
    if not root.is_dir(): raise ToolError(f"Workspace does not exist: {root}")
    return root

def _safe_resolve(repo_path: str, relative: str, *, allow_missing: bool = True) -> Path:
    root = _root(repo_path); candidate = (root / relative).resolve()
    try: common = Path(os.path.commonpath([str(root), str(candidate)]))
    except ValueError as exc: raise ToolError("Path is outside the workspace.") from exc
    if common != root: raise ToolError("Path traversal outside the workspace is blocked.")
    rel_parts = candidate.relative_to(root).parts
    if any(part in IGNORED_DIRS for part in rel_parts): raise ToolError("Direct file access to internal/ignored directories is blocked.")
    if not allow_missing and not candidate.exists(): raise ToolError(f"Path does not exist: {relative}")
    return candidate

def _relative(repo_path: str, path: Path) -> str:
    return str(path.relative_to(_root(repo_path))).replace("\\", "/")

def _sanitized_env() -> dict[str, str]:
    env = {k:v for k,v in os.environ.items() if not any(m in k.upper() for m in SECRET_ENV_MARKERS)}
    env["LOCDEX_AGENT"] = "1"; return env

def _git(repo_path: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try: return subprocess.run(["git", *args], cwd=_root(repo_path), capture_output=True, text=True, timeout=max(1,min(int(timeout),MAX_COMMAND_SECONDS)), check=False, env=_sanitized_env())
    except FileNotFoundError as exc: raise ToolError("git is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc: raise ToolError(f"git {' '.join(args)} timed out.") from exc

def list_files(repo_path: str, path: str = ".", limit: int = 200) -> dict[str, Any]:
    base=_safe_resolve(repo_path,path,allow_missing=False); root=_root(repo_path); results=[]
    if base.is_file(): return {"files":[_relative(repo_path,base)],"truncated":False}
    for current_root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not d.startswith("."))
        for name in sorted(files):
            p=Path(current_root)/name
            if p.suffix.lower() not in TEXT_EXTENSIONS and name not in {"Dockerfile","Makefile"}: continue
            results.append(str(p.relative_to(root)).replace("\\","/"))
            if len(results)>=max(1,min(int(limit),500)): return {"files":results,"truncated":True}
    return {"files":results,"truncated":False}

def read_file(repo_path: str, path: str, start_line: int = 1, end_line: int = 400) -> dict[str, Any]:
    c=_safe_resolve(repo_path,path,allow_missing=False)
    if not c.is_file(): raise ToolError(f"File does not exist: {path}")
    if c.stat().st_size>MAX_READ_BYTES: raise ToolError("File is too large for the agent read tool.")
    start=max(1,int(start_line)); end=max(start,min(int(end_line),start+499))
    try: lines=c.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc: raise ToolError("File is not UTF-8 text.") from exc
    selected=lines[start-1:end]; numbered="\n".join(f"{i}: {line}" for i,line in enumerate(selected,start=start))
    return {"path":_relative(repo_path,c),"start_line":start,"end_line":min(end,len(lines)),"total_lines":len(lines),"content":numbered}

def search_code(repo_path: str, query: str, path: str = ".", limit: int = 50) -> dict[str, Any]:
    if not query or len(query)>300: raise ToolError("Search query must be between 1 and 300 characters.")
    base=_safe_resolve(repo_path,path,allow_missing=False); root=_root(repo_path); needle=query.lower(); results=[]; files=[base] if base.is_file() else []
    if base.is_dir():
        for current_root,dirs,names in os.walk(base):
            dirs[:]=[d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            for name in names:
                p=Path(current_root)/name
                if p.suffix.lower() in TEXT_EXTENSIONS or name in {"Dockerfile","Makefile"}: files.append(p)
    cap=max(1,min(int(limit),100))
    for p in files:
        try:
            if p.stat().st_size>MAX_READ_BYTES: continue
            for n,line in enumerate(p.read_text(encoding="utf-8").splitlines(),start=1):
                if needle in line.lower():
                    results.append({"path":str(p.relative_to(root)).replace("\\","/"),"line":n,"text":line[:500]})
                    if len(results)>=cap: return {"matches":results,"truncated":True}
        except (OSError,UnicodeDecodeError): continue
    return {"matches":results,"truncated":False}

def write_file(repo_path: str, path: str, content: str) -> dict[str, Any]:
    if not isinstance(content,str): raise ToolError("write_file content must be text.")
    t=_safe_resolve(repo_path,path); t.parent.mkdir(parents=True,exist_ok=True); existed=t.exists(); t.write_text(content,encoding="utf-8")
    return {"ok":True,"path":_relative(repo_path,t),"created":not existed,"bytes":len(content.encode("utf-8"))}

def replace_in_file(repo_path: str, path: str, old: str, new: str, count: int = 1) -> dict[str, Any]:
    t=_safe_resolve(repo_path,path,allow_missing=False)
    if not t.is_file(): raise ToolError(f"File does not exist: {path}")
    if not old: raise ToolError("replace_in_file requires a non-empty old string.")
    text=t.read_text(encoding="utf-8"); occurrences=text.count(old)
    if occurrences==0: raise ToolError("Exact text to replace was not found.")
    requested=max(1,min(int(count),occurrences)); t.write_text(text.replace(old,new,requested),encoding="utf-8")
    return {"ok":True,"path":_relative(repo_path,t),"replacements":requested,"remaining_matches":occurrences-requested}

def delete_path(repo_path: str, path: str) -> dict[str, Any]:
    t=_safe_resolve(repo_path,path,allow_missing=False)
    if t.is_dir():
        if any(t.iterdir()): raise ToolError("Refusing to recursively delete a non-empty directory. Delete files explicitly.")
        t.rmdir()
    else: t.unlink()
    return {"ok":True,"path":path}

def run_command(repo_path: str, argv: list[str], cwd: str = ".", timeout: int = 120) -> dict[str, Any]:
    if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv): raise ToolError("run_command requires argv as a non-empty list of strings.")
    executable=Path(argv[0]).name.lower()
    if executable in BLOCKED_EXECUTABLES:
        if executable in {"git","gh"}: raise ToolError("Use Locdex dedicated Git tools instead of run_command for Git operations.")
        raise ToolError(f"Command is blocked in agent mode: {executable}")
    working=_safe_resolve(repo_path,cwd,allow_missing=False)
    if not working.is_dir(): raise ToolError("Command cwd must be a directory inside the workspace.")
    try: proc=subprocess.run(argv,cwd=working,capture_output=True,text=True,timeout=max(1,min(int(timeout),MAX_COMMAND_SECONDS)),check=False,env=_sanitized_env())
    except FileNotFoundError as exc: raise ToolError(f"Executable not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc: raise ToolError(f"Command timed out after {timeout}s: {shlex.join(argv)}") from exc
    combined=((proc.stdout or "")+("\n"+proc.stderr if proc.stderr else ""))[-MAX_TOOL_OUTPUT:]
    return {"ok":proc.returncode==0,"returncode":proc.returncode,"output":combined,"command":shlex.join(argv)}

def git_status(repo_path: str) -> dict[str, Any]:
    p=_git(repo_path,"status","--short","--branch"); return {"ok":p.returncode==0,"output":(p.stdout+p.stderr)[-MAX_TOOL_OUTPUT:]}

def git_diff(repo_path: str, staged: bool = False, path: str | None = None) -> dict[str, Any]:
    args=["diff"]
    if staged: args.append("--cached")
    if path: args.extend(["--",_relative(repo_path,_safe_resolve(repo_path,path,allow_missing=True))])
    p=_git(repo_path,*args); return {"ok":p.returncode==0,"output":(p.stdout+p.stderr)[-MAX_TOOL_OUTPUT:]}

def git_add(repo_path: str, paths: list[str] | None = None, all_changes: bool = False) -> dict[str, Any]:
    if all_changes: p=_git(repo_path,"add","-A")
    else:
        if not paths: raise ToolError("git_add requires paths or all_changes=true.")
        safe=[_relative(repo_path,_safe_resolve(repo_path,x,allow_missing=True)) for x in paths]; p=_git(repo_path,"add","--",*safe)
    return {"ok":p.returncode==0,"output":(p.stdout+p.stderr)[-MAX_TOOL_OUTPUT:]}

def git_commit(repo_path: str, message: str) -> dict[str, Any]:
    if not message.strip(): raise ToolError("Commit message cannot be empty.")
    p=_git(repo_path,"commit","-m",message.strip(),timeout=120); return {"ok":p.returncode==0,"output":(p.stdout+p.stderr)[-MAX_TOOL_OUTPUT:]}

def git_pull(repo_path: str, remote: str = "origin", branch: str | None = None, rebase: bool = False) -> dict[str, Any]:
    args=["pull"]+(["--rebase"] if rebase else [])+[remote]+([branch] if branch else []); p=_git(repo_path,*args,timeout=MAX_COMMAND_SECONDS); return {"ok":p.returncode==0,"output":(p.stdout+p.stderr)[-MAX_TOOL_OUTPUT:]}

def git_push(repo_path: str, remote: str = "origin", branch: str | None = None, set_upstream: bool = False) -> dict[str, Any]:
    args=["push"]
    if set_upstream: args += ["-u",remote]+([branch] if branch else [])
    else: args += [remote]+([branch] if branch else [])
    p=_git(repo_path,*args,timeout=MAX_COMMAND_SECONDS); return {"ok":p.returncode==0,"output":(p.stdout+p.stderr)[-MAX_TOOL_OUTPUT:]}

def _has_python_tests(repo_path: str) -> bool:
    root=_root(repo_path)
    for current_root,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for name in files:
            lower=name.lower()
            if lower.endswith(".py") and (lower.startswith("test_") or lower.endswith("_test.py")): return True
    return False

def run_tests(repo_path: str) -> dict[str, Any]:
    root=Path(repo_path)
    python_markers=(root/"pytest.ini",root/"pyproject.toml",root/"setup.cfg",root/"tox.ini")
    if any(m.exists() for m in python_markers) or _has_python_tests(repo_path): return run_command(repo_path,["python","-m","pytest","-q"],timeout=180)
    candidates=[(["npm","test","--","--runInBand"],root/"package.json"),(["go","test","./..."],root/"go.mod"),(["cargo","test"],root/"Cargo.toml")]
    for argv,marker in candidates:
        if marker.exists(): return run_command(repo_path,argv,timeout=180)
    return {"ok":False,"returncode":None,"output":"No supported test runner was detected automatically."}

TOOL_DESCRIPTIONS={
"list_files":"List workspace code/text files. args: path?, limit?.","read_file":"Read a UTF-8 workspace file with line numbers. args: path, start_line?, end_line?.","search_code":"Literal case-insensitive workspace search. args: query, path?, limit?.","write_file":"Create or replace a text file in the workspace immediately. args: path, content.","replace_in_file":"Replace exact text in an existing file. args: path, old, new, count?.","delete_path":"Delete a file or an empty directory in the workspace. args: path.","run_command":"Run an argv command in the workspace. args: argv (list of strings), cwd?, timeout?. No shell expansion.","run_tests":"Run the detected test suite in the current working tree. args: none.","git_status":"Show git branch and working-tree status. args: none.","git_diff":"Show unstaged or staged git diff. args: staged?, path?.","git_add":"Stage changes. Use only when the user asks for staging/commit. args: paths? or all_changes=true.","git_commit":"Commit staged changes. Use only when the user asks to commit. args: message.","git_pull":"Pull from a remote. Use only when the user asks to pull/sync. args: remote?, branch?, rebase?.","git_push":"Push commits. Use only when the user asks to push. args: remote?, branch?, set_upstream?."}

def execute_tool(repo_path: str, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    args=args or {}
    if name=="list_files": return list_files(repo_path,str(args.get("path",".")),int(args.get("limit",200)))
    if name=="read_file":
        if "path" not in args: raise ToolError("read_file requires path")
        return read_file(repo_path,str(args["path"]),int(args.get("start_line",1)),int(args.get("end_line",400)))
    if name=="search_code":
        if "query" not in args: raise ToolError("search_code requires query")
        return search_code(repo_path,str(args["query"]),str(args.get("path",".")),int(args.get("limit",50)))
    if name=="write_file":
        if "path" not in args or "content" not in args: raise ToolError("write_file requires path and content")
        return write_file(repo_path,str(args["path"]),str(args["content"]))
    if name=="replace_in_file":
        for req in ("path","old","new"):
            if req not in args: raise ToolError(f"replace_in_file requires {req}")
        return replace_in_file(repo_path,str(args["path"]),str(args["old"]),str(args["new"]),int(args.get("count",1)))
    if name=="delete_path":
        if "path" not in args: raise ToolError("delete_path requires path")
        return delete_path(repo_path,str(args["path"]))
    if name=="run_command": return run_command(repo_path,args.get("argv") or [],str(args.get("cwd",".")),int(args.get("timeout",120)))
    if name=="run_tests": return run_tests(repo_path)
    if name=="git_status": return git_status(repo_path)
    if name=="git_diff": return git_diff(repo_path,bool(args.get("staged",False)),str(args["path"]) if args.get("path") else None)
    if name=="git_add":
        paths=args.get("paths")
        if paths is not None and (not isinstance(paths,list) or not all(isinstance(p,str) for p in paths)): raise ToolError("git_add paths must be a list of strings")
        return git_add(repo_path,paths,bool(args.get("all_changes",False)))
    if name=="git_commit": return git_commit(repo_path,str(args.get("message","")))
    if name=="git_pull": return git_pull(repo_path,str(args.get("remote","origin")),str(args["branch"]) if args.get("branch") else None,bool(args.get("rebase",False)))
    if name=="git_push": return git_push(repo_path,str(args.get("remote","origin")),str(args["branch"]) if args.get("branch") else None,bool(args.get("set_upstream",False)))
    raise ToolError(f"Unknown tool: {name}")
