import json
from locdex.routing.artifact import load_artifact
from locdex.routing.artifact_scorer import ArtifactScorer
from locdex.routing.model_profile import RoutingModelProfile
from locdex.routing.task_profile import TaskProfile
from locdex.routing.updater import install_from_bytes,status
def _artifact(): return {"version":"router-v1","kind":"lookup-v1","feature_schema":1,"model_profiles_version":"1","created_at":"2026-09-30T00:00:00Z","table":{"bug_fix":{"qwen":{"success_rate":.95,"avg_cost":0,"avg_latency_ms":20000,"avg_attempts":1.1}}},"global_models":{}}
def test_artifact_scorer_overrides_rule_baseline(tmp_path):
 p=tmp_path/"router.json";p.write_text(json.dumps(_artifact()));s=ArtifactScorer(load_artifact(p));t=TaskProfile("bug_fix","python","small","single_file_or_unknown",1,1,True,False,5000,.5,.4,False,False);m=RoutingModelProfile("qwen","local",True,262144,16000,0,0);assert s.predict(t,m).predicted_success==.95
def test_router_artifact_installs_with_checksum(tmp_path,monkeypatch):
 monkeypatch.setenv("LOCDEX_CACHE_DIR",str(tmp_path));r=install_from_bytes(json.dumps(_artifact()).encode());assert r["version"]=="router-v1" and status()["installed"]
