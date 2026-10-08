from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class RouterArtifact:
    version:str; kind:str; feature_schema:int; model_profiles_version:str; created_at:str; table:dict[str,dict[str,dict[str,float]]]; global_models:dict[str,dict[str,float]]

def load_artifact(path:str|Path)->RouterArtifact:
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    return RouterArtifact(str(data["version"]),str(data.get("kind","lookup-v1")),int(data.get("feature_schema",1)),str(data.get("model_profiles_version","1")),str(data.get("created_at","")),data.get("table",{}),data.get("global_models",{}))
