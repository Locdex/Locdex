import json,pytest
from locdex.routing.router import RoutingDecision
from locdex.routing.task_profile import TaskProfile
from locdex.runtime.hardware import HardwareProfile
from locdex.telemetry.events import build_routing_event
from locdex.telemetry.queue import clear,enqueue,peek
from locdex.telemetry.sanitizer import sanitize_event
from locdex.telemetry.settings import enabled,set_enabled,set_endpoint
from locdex.telemetry.client import flush
def _event():
 t=TaskProfile("bug_fix","python","medium","multi_file",4,7,True,True,6200,.71,.8,False,False);d=RoutingDecision("qwen","local",.91,.91,0,None,"balanced","claude",{"qwen":.91,"claude":.96});h=HardwareProfile("Linux","x86_64",8,32,25,"cpu");return build_routing_event(task=t,decision=d,hardware=h,quant="q4_k_s",tests_passed=True,lint_passed=True,validator_passed=True)
def test_shared_event_contains_no_raw_content_fields():
 raw=json.dumps(_event().to_dict()).lower(); assert all(x not in raw for x in ("prompt","source_code","filename","repository","api_key","installation_id","company"))
def test_sanitizer_rejects_unknown_sensitive_field():
 d=_event().to_dict();d["prompt"]="secret"
 with pytest.raises(ValueError):sanitize_event(d)
def test_queue_is_local_and_previewable(tmp_path,monkeypatch):
 monkeypatch.setenv("LOCDEX_CACHE_DIR",str(tmp_path/"cache"));clear();enqueue(_event().to_dict());assert peek()[0]["model_id"]=="qwen"
def test_telemetry_disabled_by_default_and_no_endpoint_means_no_send(tmp_path,monkeypatch):
 monkeypatch.setenv("LOCDEX_CONFIG_DIR",str(tmp_path/"config"));monkeypatch.setenv("LOCDEX_CACHE_DIR",str(tmp_path/"cache"));monkeypatch.delenv("LOCDEX_TELEMETRY_MODE",raising=False);assert not enabled();set_enabled(True);set_endpoint("");enqueue(_event().to_dict());assert flush()["reason"]=="no_endpoint" and len(peek())==1
def test_research_consent_is_separate_mode(tmp_path,monkeypatch):
 from locdex.telemetry.settings import mode,set_mode
 monkeypatch.setenv("LOCDEX_CONFIG_DIR",str(tmp_path/"config"));monkeypatch.delenv("LOCDEX_TELEMETRY_MODE",raising=False);set_mode("research");assert mode()=="research"
