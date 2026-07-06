from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.agents.schema import AgentTaskPromptInput, AgentTaskView


def test_agent_task_prompt_input_accepts_prompt_fields() -> None:
    prompt_input = AgentTaskPromptInput(
        task_id="repair_jsonl_deduper",
        instruction="Fix the JSONL deduper.",
        allowed_tools=["read_file", "write_file", "run_tests"],
        public_checks=["uv run pytest tests/test_public.py"],
        max_turns=8,
        timeout_seconds=30,
        network="off",
    )

    assert prompt_input.task_id == "repair_jsonl_deduper"
    assert prompt_input.allowed_tools == ["read_file", "write_file", "run_tests"]
    assert prompt_input.network == "off"


def test_agent_task_prompt_input_rejects_workspace_path(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "task_id": "repair_jsonl_deduper",
        "instruction": "Fix the JSONL deduper.",
        "workspace_path": tmp_path / "workspace",
        "allowed_tools": ["read_file", "write_file", "run_tests"],
        "public_checks": ["uv run pytest tests/test_public.py"],
        "max_turns": 8,
        "timeout_seconds": 30,
        "network": "off",
    }

    with pytest.raises(ValidationError):
        AgentTaskPromptInput.model_validate(payload)


def test_agent_task_view_accepts_visible_task_fields(tmp_path: Path) -> None:
    view = AgentTaskView(
        task_id="repair_jsonl_deduper",
        instruction="Fix the JSONL deduper.",
        workspace_path=tmp_path / "workspace",
        allowed_tools=["read_file", "write_file", "run_tests"],
        public_checks=["uv run pytest tests/test_public.py"],
        max_turns=8,
        timeout_seconds=30,
        network="off",
    )

    assert view.task_id == "repair_jsonl_deduper"
    assert view.workspace_path == tmp_path / "workspace"
    assert view.allowed_tools == ["read_file", "write_file", "run_tests"]
    assert view.network == "off"


@pytest.mark.parametrize(
    "field_name",
    [
        "hidden_validators",
        "controls",
        "leakage_canary",
        "task_manifest_path",
        "task_pack_path",
        "oracle_patch",
        "scoring",
    ],
)
def test_agent_task_view_rejects_private_evaluator_fields(
    tmp_path: Path,
    field_name: str,
) -> None:
    payload: dict[str, object] = {
        "task_id": "repair_jsonl_deduper",
        "instruction": "Fix the JSONL deduper.",
        "workspace_path": tmp_path / "workspace",
        "allowed_tools": ["read_file", "write_file", "run_tests"],
        "public_checks": ["uv run pytest tests/test_public.py"],
        "max_turns": 8,
        "timeout_seconds": 30,
        "network": "off",
    }
    payload[field_name] = "private"

    with pytest.raises(ValidationError):
        AgentTaskView.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("task_id", ""),
        ("instruction", ""),
        ("allowed_tools", []),
        ("public_checks", []),
        ("max_turns", 0),
        ("timeout_seconds", 0),
        ("network", "on"),
    ],
)
def test_agent_task_view_rejects_invalid_visible_fields(
    tmp_path: Path,
    field_name: str,
    value: object,
) -> None:
    payload: dict[str, object] = {
        "task_id": "repair_jsonl_deduper",
        "instruction": "Fix the JSONL deduper.",
        "workspace_path": tmp_path / "workspace",
        "allowed_tools": ["read_file", "write_file", "run_tests"],
        "public_checks": ["uv run pytest tests/test_public.py"],
        "max_turns": 8,
        "timeout_seconds": 30,
        "network": "off",
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        AgentTaskView.model_validate(payload)
