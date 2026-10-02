from __future__ import annotations
import os, platform
from dataclasses import dataclass
@dataclass(frozen=True)
class HardwareProfile:
    system:str; machine:str; cpu_count:int; total_ram_gb:float|None; available_ram_gb:float|None; backend:str
def _linux_ram():
    try:
        v={}
        with open("/proc/meminfo","r",encoding="utf-8") as f:
            for line in f:
                k,x=line.split(":",1);v[k]=int(x.strip().split()[0])
        t=v.get("MemTotal");a=v.get("MemAvailable");return ((t/1024/1024) if t else None,(a/1024/1024) if a else None)
    except Exception:return None,None
def detect_hardware():
    s=platform.system();t=a=None
    if s=="Linux":t,a=_linux_ram()
    b="metal" if s=="Darwin" and platform.machine().lower() in {"arm64","aarch64"} else "cpu"
    return HardwareProfile(s,platform.machine(),os.cpu_count() or 1,t,a,b)
