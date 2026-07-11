from typing import Literal


AgentAuditField = Literal[
    "agent_run_status",
    "agent_error_class",
    "prompt_loop_status",
    "prompt_loop_error_class",
    "model_finish_reasons",
    "tool_results",
    "attempt_status",
    "public_status",
    "hidden_status",
]
ScorerAuditField = Literal[
    "attempt_status",
    "public_status",
    "hidden_status",
]
