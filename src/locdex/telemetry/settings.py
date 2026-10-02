import json,os
from pathlib import Path
try: from platformdirs import user_config_dir
except ImportError:user_config_dir=None
def _dir():
    d=Path(user_config_dir("locdex","Locdex")) if user_config_dir else Path.home()/".config"/"locdex"
    return Path(os.environ.get("LOCDEX_CONFIG_DIR",str(d))).expanduser()
def _path():return _dir()/"telemetry.json"
def load():
    try:
        d=json.loads(_path().read_text(encoding="utf-8"));return d if isinstance(d,dict) else {}
    except Exception:return {}
def save(data):
    p=_path();p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8")
def mode():
    raw=os.environ.get("LOCDEX_TELEMETRY_MODE")
    value=raw.strip().lower() if raw else str(load().get("mode","basic" if load().get("enabled",False) else "off")).lower()
    return value if value in {"off","basic","research"} else "off"
def enabled():return mode() in {"basic","research"}
def set_mode(value):
    value=value.strip().lower()
    if value not in {"off","basic","research"}:raise ValueError("telemetry mode must be off, basic, or research")
    d=load();d.pop("enabled",None);d["mode"]=value;save(d)
def set_enabled(value):set_mode("basic" if value else "off")
def endpoint():return os.environ.get("LOCDEX_TELEMETRY_ENDPOINT",str(load().get("endpoint",""))).strip()
def set_endpoint(value):
    d=load();d["endpoint"]=value.strip();save(d)
