import json

from agentenv.artifacts import ArtifactType


def test_artifact_type_values_are_stable_json_strings() -> None:
    assert ArtifactType.SCORER_ATTEMPT == "scorer_attempt"
    assert ArtifactType.AGENT_ATTEMPT == "agent_attempt"
    assert ArtifactType.EVAL_RUN == "eval_run"
    assert ArtifactType.EVAL_SUITE == "eval_suite"
    assert ArtifactType.CONTROL_CALIBRATION == "control_calibration"
    assert ArtifactType.REPLAY_RUN == "replay_run"
    assert json.dumps({"artifact_type": ArtifactType.EVAL_RUN}) == (
        '{"artifact_type": "eval_run"}'
    )
