from dataclasses import dataclass
from ..security import RiskClass
@dataclass(frozen=True)
class ToolDefinition:name:str;risk:RiskClass;description:str
TOOLS={"read_file":ToolDefinition("read_file",RiskClass.READ,"Read a workspace file."),"search_repo":ToolDefinition("search_repo",RiskClass.READ,"Search workspace text."),"write_file":ToolDefinition("write_file",RiskClass.WRITE,"Write a workspace file."),"run_command":ToolDefinition("run_command",RiskClass.EXECUTE,"Run a bounded development command."),"git_commit":ToolDefinition("git_commit",RiskClass.GIT_WRITE,"Commit staged changes.")}
