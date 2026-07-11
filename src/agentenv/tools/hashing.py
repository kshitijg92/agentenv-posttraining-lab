import json
from collections.abc import Mapping

import xxhash

from agentenv.tools.schema import ToolInput


def hash_tool_arguments(arguments: Mapping[str, object]) -> str:
    payload = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return f"xxh64:{xxhash.xxh64_hexdigest(payload.encode())}"


def hash_tool_input(tool_input: ToolInput) -> str:
    return hash_tool_arguments(tool_input.model_dump(mode="json"))
