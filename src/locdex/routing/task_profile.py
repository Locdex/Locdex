from dataclasses import asdict,dataclass
from pathlib import Path
import re
@dataclass(frozen=True)
class TaskProfile:
    task_class:str; language:str; repo_size_bucket:str; requested_change:str; estimated_files:int; dependency_fanout:int; has_tests:bool; has_stacktrace:bool; context_estimate:int; reasoning_complexity:float; tool_intensity:float; requires_vision:bool; requires_long_context:bool; current_attempt:int=1; previous_model_failed:str|None=None
    def to_features(self):return asdict(self)
def _language(r):
    if (r/"pyproject.toml").exists():return "python"
    if (r/"package.json").exists():return "typescript_javascript"
    if (r/"go.mod").exists():return "go"
    if (r/"Cargo.toml").exists():return "rust"
    return "unknown"
def classify_task(t):
    x=t.lower()
    if any(k in x for k in ("architecture","migration","redesign")):return "architecture"
    if any(k in x for k in ("debug","stack trace","runtime error")):return "debugging"
    if any(k in x for k in ("test","pytest","coverage")):return "testing"
    if any(k in x for k in ("refactor","cleanup")):return "refactor"
    if any(k in x for k in ("fix","bug","error","failure")):return "bug_fix"
    if any(k in x for k in ("find implementation","find reference","where is","locate")):return "repo_navigation"
    if any(k in x for k in ("explain","understand","how does")):return "code_explanation"
    if any(k in x for k in ("shell","build","package","deploy","git ")):return "tool_heavy"
    if any(k in x for k in ("create module","new class","new function","implement feature","add feature")):return "code_generation"
    if any(k in x for k in ("rename","config","modify","update")):return "small_edit"
    return "other"
def profile_task(task,repo_path=".",*,context_estimate=0,current_attempt=1,previous_model_failed=None):
    r=Path(repo_path).resolve(); cls=classify_task(task); lower=task.lower(); multi=any(k in lower for k in ("multi-file","across","several files","architecture","migration")); stack=bool(re.search(r"traceback|stack trace|exception|error:\s",lower)); tests=any((r/x).exists() for x in ("tests","test","pytest.ini","package.json","go.mod"))
    count=sum(1 for p in r.rglob("*") if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts); size="small" if count<100 else "medium" if count<600 else "large"
    cm={"repo_navigation":.2,"code_explanation":.25,"small_edit":.2,"code_generation":.5,"bug_fix":.6,"refactor":.65,"testing":.5,"debugging":.75,"architecture":.9,"tool_heavy":.6,"other":.45}; comp=min(1,cm.get(cls,.45)+(.1 if multi else 0)+(.05 if stack else 0))
    return TaskProfile(cls,_language(r),size,"multi_file" if multi else "single_file_or_unknown",5 if multi else 2 if cls in {"bug_fix","refactor","testing","debugging"} else 1,8 if multi else 4 if cls in {"bug_fix","refactor","debugging"} else 1,tests,stack,int(context_estimate),comp,.8 if cls=="tool_heavy" else .65 if cls in {"debugging","testing"} else .4,False,context_estimate>32000,max(1,current_attempt),previous_model_failed)
