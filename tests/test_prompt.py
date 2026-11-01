from pathlib import Path

from free_hand.executor import build_registry
from free_hand.prompt import make_system_prompt


def test_prompt_includes_workflow_and_registered_tools(tmp_path: Path):
    prompt = make_system_prompt(build_registry(tmp_path, {}))
    assert "only one valid JSON object" in prompt
    assert "tool_choice" in prompt
    for name in ("read_file", "write_file", "edit_file", "git_status", "git_diff", "git_stage", "git_commit", "run_command"):
        assert f'"name": "{name}"' in prompt
    assert "Never include explanatory text outside the JSON object" in prompt


def test_prompt_teaches_valid_json_escaping(tmp_path: Path):
    prompt = make_system_prompt(build_registry(tmp_path, {}))
    assert '"pattern": "*"' in prompt
    assert '"pattern": "\\*"' in prompt
    assert "JSON escaping is strict" in prompt
    assert "must encode line breaks as `\\n`" in prompt
    assert "Never return Python-style strings" in prompt
