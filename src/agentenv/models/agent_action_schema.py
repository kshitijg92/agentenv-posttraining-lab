from copy import deepcopy


_AGENT_ACTION_JSON_SCHEMA: dict[str, object] = {
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "const": "tool_call"},
                "tool_name": {"type": "string", "minLength": 1},
                "arguments": {"type": "object"},
            },
            "required": ["action", "tool_name", "arguments"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "const": "final_answer"},
                "text": {"type": "string", "minLength": 1},
            },
            "required": ["action", "text"],
            "additionalProperties": False,
        },
    ]
}


def agent_action_json_schema() -> dict[str, object]:
    return deepcopy(_AGENT_ACTION_JSON_SCHEMA)


def openai_agent_action_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "agent_action",
            "strict": True,
            "schema": agent_action_json_schema(),
        },
    }
