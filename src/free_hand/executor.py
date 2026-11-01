from pathlib import Path
from typing import Any

from .registry import Registry, Tool
from .tools.commands import run_command
from .tools.filesystem import edit_file, list_files, read_file, search_files, write_file
from .tools.git_tools import git_commit, git_diff, git_stage, git_status


def build_registry(root: Path, config: dict[str, Any]) -> Registry:
    registry = Registry()
    timeout = int(config.get("command_timeout_seconds", 30))

    def params(properties, required):
        return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}

    registry.register(Tool("read_file", "Read a UTF-8 project file; secret-like paths are blocked.", params({"path": {"type": "string"}}, ["path"]), lambda a: read_file(root, a["path"])))
    registry.register(Tool("list_files", "List permitted project files matching a glob pattern.", params({"pattern": {"type": "string"}}, []), lambda a: "\n".join(list_files(root, a.get("pattern", "**/*")))))
    registry.register(Tool("search_files", "Search project files with a smart-case regular expression when literal=false; literal=true searches exact text.", params({"query": {"type": "string"}, "literal": {"type": "boolean"}}, ["query"]), lambda a: "\n".join(search_files(root, a["query"], a.get("literal", True)))))
    registry.register(Tool("write_file", "Write UTF-8 content to a new project file; refuses to overwrite existing files and requires approval.", params({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), lambda a: write_file(root, a["path"], a["content"]), "write"))
    registry.register(Tool("edit_file", "Replace one exact text occurrence in an existing UTF-8 project file; requires approval.", params({"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, ["path", "old_text", "new_text"]), lambda a: edit_file(root, a["path"], a["old_text"], a["new_text"]), "write"))
    registry.register(Tool("git_status", "Inspect the current Git working tree status.", params({}, []), lambda a: git_status(root)))
    registry.register(Tool("git_diff", "Inspect working-tree or staged Git changes; untracked files are listed by status, not diff.", params({"staged": {"type": "boolean"}, "paths": {"type": "array", "items": {"type": "string"}}}, []), lambda a: git_diff(root, a.get("staged", False), a.get("paths", []))))
    registry.register(Tool("git_stage", "Stage explicitly selected project paths; requires approval. Never pass broad paths unless explicitly intended.", params({"paths": {"type": "array", "items": {"type": "string"}}}, ["paths"]), lambda a: git_stage(root, a["paths"]), "git"))
    registry.register(Tool("git_commit", "Commit staged changes using the supplied message or a default message; requires approval. Review staged diff first.", params({"message": {"type": "string"}}, []), lambda a: git_commit(root, a.get("message")), "git"))
    registry.register(Tool("run_command", "Run an approved command using argv in the project directory, without a shell.", params({"argv": {"type": "array", "items": {"type": "string"}}}, ["argv"]), lambda a: run_command(root, a["argv"], timeout), "command"))
    return registry


def validate_arguments(tool: Tool, args: dict[str, Any]) -> None:
    props = tool.parameters.get("properties", {})
    required = tool.parameters.get("required", [])
    extra, missing = set(args) - set(props), set(required) - set(args)
    if extra:
        raise ValueError(f"Unknown argument(s): {', '.join(sorted(extra))}")
    if missing:
        raise ValueError(f"Missing argument(s): {', '.join(sorted(missing))}")
    for key, value in args.items():
        kind = props[key].get("type")
        if kind == "string" and not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        if kind == "boolean" and not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        if kind == "array" and (not isinstance(value, list) or not all(isinstance(x, str) for x in value)):
            raise ValueError(f"{key} must be an array of strings")


def execute_response(response: dict[str, Any], registry: Registry, approve, output_limit: int = 20_000) -> dict[str, Any]:
    results = []
    halted = False
    for call in response["tool_calls"]:
        call_id, name, args = call["id"], call["function"]["name"], call["function"]["arguments"]
        if halted:
            results.append({"id": call_id, "name": name, "status": "skipped", "output": "Skipped because execution halted."})
            continue
        tool = registry.get(name)
        if tool is None:
            results.append({"id": call_id, "name": name, "status": "failure", "error": f"Unknown tool: {name}"})
            halted = True
            continue
        try:
            validate_arguments(tool, args)
            if tool.risk != "read" and not approve(tool, args):
                results.append({"id": call_id, "name": name, "status": "rejected", "output": "User rejected this operation."})
                halted = True
                continue
            value = tool.handler(args)
            if len(value) > output_limit:
                value = value[:output_limit] + f"\n...[truncated at {output_limit} characters]"
            results.append({"id": call_id, "name": name, "status": "success", "output": value})
        except Exception as exc:
            results.append({"id": call_id, "name": name, "status": "failure", "error": f"{type(exc).__name__}: {exc}"})
            halted = True
    return {"version": 1, "results": results, "final_message": response["final_message"], "next_action": "Paste these execution results back into your AI chat assistant to continue."}
