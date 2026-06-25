import pytest
from pydantic import ValidationError

from agentenv.agents.schema import FinalAnswerAction, ToolCallAction
from agentenv.agents.schema import parse_agent_action


def test_parse_agent_action_accepts_tool_call() -> None:
    action = parse_agent_action(
        """
        {
          "action": "tool_call",
          "tool_name": "read_file",
          "arguments": {
            "path": "src/foo.py",
            "line": 10,
            "strict": true,
            "score": 1.0,
            "optional": null
          }
        }
        """
    )

    assert isinstance(action, ToolCallAction)
    assert action.tool_name == "read_file"
    assert action.arguments["path"] == "src/foo.py"
    assert action.arguments["strict"] is True


def test_parse_agent_action_accepts_tool_call_with_default_arguments() -> None:
    action = parse_agent_action(
        """
        {
          "action": "tool_call",
          "tool_name": "run_tests"
        }
        """
    )

    assert isinstance(action, ToolCallAction)
    assert action.arguments == {}


def test_parse_agent_action_accepts_final_answer() -> None:
    action = parse_agent_action(
        """
        {
          "action": "final_answer",
          "text": "done"
        }
        """
    )

    assert isinstance(action, FinalAnswerAction)
    assert action.text == "done"


def test_parse_agent_action_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="model output is not valid JSON"):
        parse_agent_action('{"action": "tool_call"')


def test_parse_agent_action_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        parse_agent_action(
            """
            {
              "action": "think",
              "text": "I should inspect the file."
            }
            """
        )


def test_parse_agent_action_rejects_empty_tool_name_and_text() -> None:
    with pytest.raises(ValidationError):
        parse_agent_action(
            """
            {
              "action": "tool_call",
              "tool_name": ""
            }
            """
        )

    with pytest.raises(ValidationError):
        parse_agent_action(
            """
            {
              "action": "final_answer",
              "text": ""
            }
            """
        )


def test_parse_agent_action_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        parse_agent_action(
            """
            {
              "action": "tool_call",
              "tool_name": "read_file",
              "arguments": {"path": "src/foo.py"},
              "text": "not allowed"
            }
            """
        )

    with pytest.raises(ValidationError):
        parse_agent_action(
            """
            {
              "action": "final_answer",
              "text": "done",
              "tool_name": "read_file"
            }
            """
        )


def test_parse_agent_action_rejects_nested_arguments() -> None:
    with pytest.raises(ValidationError):
        parse_agent_action(
            """
            {
              "action": "tool_call",
              "tool_name": "read_file",
              "arguments": {
                "path": {"nested": "not allowed"}
              }
            }
            """
        )

    with pytest.raises(ValidationError):
        parse_agent_action(
            """
            {
              "action": "tool_call",
              "tool_name": "read_file",
              "arguments": {
                "paths": ["src/foo.py"]
              }
            }
            """
        )
