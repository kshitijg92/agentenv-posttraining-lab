import re
from collections.abc import Callable

import pytest

from agentenv.ids import (
    new_agent_attempt_id,
    new_eval_attempt_id,
    new_eval_run_id,
    new_eval_suite_id,
    new_replay_run_id,
    new_scorer_attempt_id,
)


@pytest.mark.parametrize(
    ("factory", "prefix"),
    [
        (new_eval_suite_id, "eval_suite"),
        (new_eval_run_id, "eval_run"),
        (new_eval_attempt_id, "eval_attempt"),
        (new_agent_attempt_id, "agent_attempt"),
        (new_scorer_attempt_id, "scorer_attempt"),
        (new_replay_run_id, "replay_run"),
    ],
)
def test_id_helpers_use_typed_prefixes(
    factory: Callable[[], str],
    prefix: str,
) -> None:
    generated_id = factory()

    assert re.fullmatch(rf"{prefix}_[0-9a-f]{{32}}", generated_id)


@pytest.mark.parametrize(
    "factory",
    [
        new_eval_suite_id,
        new_eval_run_id,
        new_eval_attempt_id,
        new_agent_attempt_id,
        new_scorer_attempt_id,
        new_replay_run_id,
    ],
)
def test_id_helpers_generate_unique_values_per_helper(
    factory: Callable[[], str],
) -> None:
    generated_ids = {factory() for _ in range(20)}

    assert len(generated_ids) == 20
