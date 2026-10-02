from pathlib import Path
from locdex.agent import AgentEngine
from locdex.context import ContextBudget,ContextCompiler
from locdex.models import MODEL_PROFILES
from locdex.routing import CostBudget,plan_execution,within_budget
from locdex.security import RiskClass,native_authorize,redact_secrets

def test_model_profiles_preserve_qwen_and_kimi():
 assert "35B-A3B" in MODEL_PROFILES["qwen"].display_name; assert "9B Kimi-K3" in MODEL_PROFILES["kimi"].display_name; assert MODEL_PROFILES["kimi"].status=="experimental"
def test_secret_redaction():
 text,count=redact_secrets('API_KEY="abcdef"'); assert count==1 and "abcdef" not in text and "REDACTED_SECRET" in text
def test_git_write_requires_explicit_intent():
 assert not native_authorize(RiskClass.GIT_WRITE,False).allowed; assert native_authorize(RiskClass.GIT_WRITE,True).allowed
def test_context_compiler_builds_bounded_pack(tmp_path):
 (tmp_path/"auth.py").write_text("def login(token):\n    return token\n"); pack=ContextCompiler().compile(str(tmp_path),"fix login",ContextBudget(max_input_tokens=200)); assert pack.total_tokens<=200
def test_cloud_context_redacts_task_secret(tmp_path):
 (tmp_path/"app.py").write_text("x=1\n"); pack=ContextCompiler().compile(str(tmp_path),"password=hunter2 fix auth",cloud=True); assert "hunter2" not in "\n".join(i.content for i in pack.items) and pack.redactions>=1
def test_execution_plan_is_local_first():
 assert plan_execution(local_model="qwen",cloud_enabled=False).route=="local"; assert plan_execution(local_model="qwen",cloud_enabled=True,complexity="hard").route=="local_then_cloud"
def test_cost_controller(): assert within_budget(.2,CostBudget(max_task_cost=.3)) and not within_budget(.4,CostBudget(max_task_cost=.3))
def test_agent_prepare_uses_context_and_plan(tmp_path):
 (tmp_path/"main.py").write_text("def run():\n    pass\n"); result=AgentEngine().prepare("inspect run",str(tmp_path)); assert result["plan"].route=="local" and result["context"].total_tokens>0
