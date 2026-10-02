from locdex.routing import LearnedRouter,RoutingPolicy,RoutingSession,cloud_candidate,profile_task
from locdex.routing.model_profile import RoutingModelProfile
from locdex.routing.task_profile import classify_task
def local(mid):return RoutingModelProfile(mid,"local",True,262144,16000,0,0,average_latency_ms=30000,tool_call_quality=.85,reasoning_strength=.8)
def test_task_taxonomy_bug_and_architecture(): assert classify_task("fix the failing bug")=="bug_fix" and classify_task("redesign the routing architecture")=="architecture"
def test_balanced_prefers_good_local_model(tmp_path):
 t=profile_task("fix a small bug",str(tmp_path),context_estimate=5000);m=[local("qwen"),cloud_candidate(provider="anthropic",model_id="claude",input_cost=3,output_cost=15,reasoning_strength=.95)];d=LearnedRouter().route(task=t,models=m,policy=RoutingPolicy(mode="balanced",allow_cloud=True,allowed_providers=("anthropic",)),session=RoutingSession());assert d.model=="qwen" and d.predicted_cost==0
def test_local_only_eliminates_cloud(tmp_path):
 t=profile_task("architecture redesign",str(tmp_path),context_estimate=9000);m=[local("qwen"),cloud_candidate(provider="anthropic",model_id="claude",input_cost=3,output_cost=15)];d=LearnedRouter().route(task=t,models=m,policy=RoutingPolicy(mode="local_only",allow_cloud=True),session=RoutingSession());assert d.route=="local"
def test_session_switching_penalty_exists():
 s=RoutingSession(current_model="qwen");assert s.switching_penalty("qwen")==0 and s.switching_penalty("claude")>0
