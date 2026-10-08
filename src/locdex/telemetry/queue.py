import json,os
from pathlib import Path
try: from platformdirs import user_cache_dir
except ImportError:user_cache_dir=None
from .sanitizer import sanitize_event
def _path():
    d=Path(user_cache_dir("locdex","Locdex")) if user_cache_dir else Path.home()/".cache"/"locdex"
    return Path(os.environ.get("LOCDEX_CACHE_DIR",str(d))).expanduser()/"telemetry"/"queue.jsonl"
def enqueue(event):
    clean=sanitize_event(event);p=_path();p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("a",encoding="utf-8") as f:f.write(json.dumps(clean,separators=(",",":"),sort_keys=True)+"\n")
def peek(limit=50):
    p=_path()
    if not p.exists():return []
    out=[]
    for line in p.read_text(encoding="utf-8").splitlines()[:max(1,min(limit,100))]:
        try:out.append(json.loads(line))
        except json.JSONDecodeError:pass
    return out
def pop(limit=50):
    p=_path();rows=peek(limit)
    if not rows or not p.exists():return rows
    lines=p.read_text(encoding="utf-8").splitlines();rem=lines[len(rows):]
    if rem:p.write_text("\n".join(rem)+"\n",encoding="utf-8")
    else:p.unlink(missing_ok=True)
    return rows
def prepend(events):
    if not events:return
    p=_path();p.parent.mkdir(parents=True,exist_ok=True);existing=p.read_text(encoding="utf-8") if p.exists() else "";prefix="".join(json.dumps(sanitize_event(e),separators=(",",":"),sort_keys=True)+"\n" for e in events);p.write_text(prefix+existing,encoding="utf-8")
def clear():_path().unlink(missing_ok=True)
