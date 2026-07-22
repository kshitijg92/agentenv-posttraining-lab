from uuid import uuid4


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def new_eval_suite_id() -> str:
    return _new_id("eval_suite")


def new_eval_run_id() -> str:
    return _new_id("eval_run")


def new_eval_attempt_id() -> str:
    return _new_id("eval_attempt")


def new_agent_attempt_id() -> str:
    return _new_id("agent_attempt")


def new_scorer_attempt_id() -> str:
    return _new_id("scorer_attempt")


def new_scorer_audit_run_id() -> str:
    return _new_id("scorer_audit")


def new_agent_task_audit_run_id() -> str:
    return _new_id("agent_task_audit")


def new_harness_audit_run_id() -> str:
    return _new_id("harness_audit")


def new_replay_run_id() -> str:
    return _new_id("replay_run")


def new_message_id() -> str:
    return _new_id("message")


def new_positive_sft_lora_training_run_id() -> str:
    return _new_id("positive_sft_lora_run")
