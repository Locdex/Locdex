import hashlib,json,os
from pathlib import Path
import requests
try: from platformdirs import user_cache_dir
except ImportError:user_cache_dir=None
from .artifact import load_artifact
def router_dir():
    d=Path(user_cache_dir("locdex","Locdex")) if user_cache_dir else Path.home()/".cache"/"locdex"
    return Path(os.environ.get("LOCDEX_CACHE_DIR",str(d))).expanduser()/"router"
def active_path():return router_dir()/"router.json"
def status():
    p=active_path()
    if not p.exists():return {"installed":False,"version":"rules-v0","kind":"rules"}
    try:a=load_artifact(p);return {"installed":True,"version":a.version,"kind":a.kind,"path":str(p)}
    except Exception as e:return {"installed":False,"version":"rules-v0","kind":"rules","error":str(e)}
def install_from_bytes(data,expected_sha256=None):
    d=hashlib.sha256(data).hexdigest()
    if expected_sha256 and d.lower()!=expected_sha256.lower():raise ValueError("Router artifact checksum mismatch.")
    t=router_dir()/"router.tmp";t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes(data);a=load_artifact(t);t.replace(active_path());return {"installed":True,"version":a.version,"sha256":d,"path":str(active_path())}
def update_from_manifest(manifest_url=None,timeout=10.0):
    url=(manifest_url or os.environ.get("LOCDEX_ROUTER_MANIFEST_URL","")).strip()
    if not url:return {"updated":False,"reason":"no_manifest_url"}
    m=requests.get(url,timeout=timeout);m.raise_for_status();meta=m.json()
    if str(meta.get("version"))==str(status().get("version")):return {"updated":False,"reason":"current","version":meta.get("version")}
    a=requests.get(str(meta["artifact_url"]),timeout=timeout);a.raise_for_status();r=install_from_bytes(a.content,str(meta.get("sha256") or "") or None);r["updated"]=True;return r
