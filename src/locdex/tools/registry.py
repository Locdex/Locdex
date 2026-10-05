from __future__ import annotations

from dataclasses import dataclass

from ..security import RiskClass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    risk: RiskClass
    description: str


TOOLS = {
    "list_files": ToolDefinition("list_files", RiskClass.READ, "List workspace code/text files."),
    "read_file": ToolDefinition("read_file", RiskClass.READ, "Read a UTF-8 workspace file with line numbers."),
    "search_code": ToolDefinition("search_code", RiskClass.READ, "Search workspace text literally."),
    "find_symbol": ToolDefinition("find_symbol", RiskClass.READ, "Find Python symbol definitions by exact name."),
    "find_references": ToolDefinition("find_references", RiskClass.READ, "Find Python references to an exact symbol."),
    "get_symbol_source": ToolDefinition("get_symbol_source", RiskClass.READ, "Retrieve the exact source range for a Python symbol."),
    "get_reference_context": ToolDefinition("get_reference_context", RiskClass.READ, "Retrieve small exact source ranges around symbol references."),
    "related_files": ToolDefinition("related_files", RiskClass.READ, "Rank files related to the current task using symbols/imports/tests."),
    "write_file": ToolDefinition("write_file", RiskClass.WRITE, "Create or replace a workspace text file."),
    "replace_in_file": ToolDefinition("replace_in_file", RiskClass.WRITE, "Replace exact text in a workspace file."),
    "replace_symbol": ToolDefinition("replace_symbol", RiskClass.WRITE, "Replace one top-level Python function/class by symbol name using syntax-checked source."),
    "insert_after_symbol": ToolDefinition("insert_after_symbol", RiskClass.WRITE, "Insert syntax-checked Python source after a named top-level function/class."),
    "delete_path": ToolDefinition("delete_path", RiskClass.WRITE, "Delete a file or empty directory."),
    "run_command": ToolDefinition("run_command", RiskClass.EXECUTE, "Run a bounded argv development command."),
    "run_tests": ToolDefinition("run_tests", RiskClass.EXECUTE, "Run the detected project test suite."),
    "mcp_list_tools": ToolDefinition(
        "mcp_list_tools",
        RiskClass.NETWORK,
        "List tools exposed by a user-configured MCP server.",
    ),
    "mcp_call": ToolDefinition(
        "mcp_call",
        RiskClass.NETWORK,
        "Call one tool on a user-configured MCP server.",
    ),
    "git_status": ToolDefinition("git_status", RiskClass.READ, "Read Git working-tree status."),
    "git_diff": ToolDefinition("git_diff", RiskClass.READ, "Read Git diff."),
    "git_add": ToolDefinition("git_add", RiskClass.GIT_WRITE, "Stage explicitly requested changes."),
    "git_commit": ToolDefinition("git_commit", RiskClass.GIT_WRITE, "Commit explicitly requested staged changes."),
    "git_pull": ToolDefinition("git_pull", RiskClass.GIT_WRITE, "Pull only with explicit current-user intent."),
    "git_push": ToolDefinition("git_push", RiskClass.GIT_WRITE, "Push only with explicit current-user intent."),
}
