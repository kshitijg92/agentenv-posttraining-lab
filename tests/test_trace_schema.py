import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.tracing.schema import (
    TRACE_SCHEMA_VERSION,
    AttemptTraceProvenance,
    EvalTraceProvenance,
    ReplayTraceProvenance,
    TraceEvent,
)
from agentenv.tracing.validate import (
    load_trace_events,
    validate_trace_events,
    validate_trace_file,
)


def test_trace_event_schema_accepts_minimal_event() -> None:
    event = TraceEvent(
        schema_version=TRACE_SCHEMA_VERSION,
        event_index=0,
        timestamp_utc="2026-06-20T00:00:00Z",
        event_type="replay_started",
        provenance_config=ReplayTraceProvenance(replay_run_id="replay_run_001"),
    )

    assert event.schema_version == "trace_v0"
    assert event.event_index == 0
    assert event.input_payload is None
    assert isinstance(event.provenance_config, ReplayTraceProvenance)
    assert event.provenance_config.replay_run_id == "replay_run_001"


def test_trace_event_schema_accepts_optional_payloads() -> None:
    event = TraceEvent(
        schema_version=TRACE_SCHEMA_VERSION,
        event_index=1,
        timestamp_utc="2026-06-20T00:00:01Z",
        event_type="command_finished",
        provenance_config=AttemptTraceProvenance(
            scorer_attempt_id="scorer_attempt_001",
            task_id="task_001",
            phase="public_check",
            name="pytest_public",
        ),
        input_payload={"command": ["uv", "run", "pytest"]},
        output_payload={"returncode": 0},
        payload_refs={"stdout": "stdout.txt"},
        payload_hashes={"stdout": "xxh64:abc123"},
    )

    assert event.payload_refs == {"stdout": "stdout.txt"}
    assert event.payload_hashes == {"stdout": "xxh64:abc123"}
    assert isinstance(event.provenance_config, AttemptTraceProvenance)
    assert event.provenance_config.phase == "public_check"


def test_trace_event_schema_accepts_eval_event() -> None:
    event = TraceEvent(
        schema_version=TRACE_SCHEMA_VERSION,
        event_index=1,
        timestamp_utc="2026-06-20T00:00:01Z",
        event_type="eval_attempt_finished",
        provenance_config=EvalTraceProvenance(
            eval_run_id="eval_run_001",
            config_hash="xxh64:abc123",
            config_name="scorer_control_policies",
            policy="oracle",
            task_id="toy_python_fix_001",
            task_index=0,
            attempt_index=0,
            eval_attempt_id="eval_attempt_001",
            scorer_attempt_id="scorer_attempt_001",
        ),
        output_payload={"status": "PASS"},
    )

    assert isinstance(event.provenance_config, EvalTraceProvenance)
    assert event.provenance_config.policy == "oracle"


def test_trace_event_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            {
                "schema_version": "trace_v999",
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "replay_started",
                "provenance_config": {"replay_run_id": "replay_run_001"},
            }
        )


def test_validate_trace_file_accepts_sequential_events(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    event_types = ["replay_started", "replay_finished"]
    trace_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "schema_version": TRACE_SCHEMA_VERSION,
                    "event_index": index,
                    "timestamp_utc": f"2026-06-20T00:00:0{index}Z",
                    "event_type": event_types[index],
                    "provenance_config": {"replay_run_id": "replay_run_001"},
                },
                sort_keys=True,
            )
            for index in range(2)
        )
        + "\n"
    )

    events = load_trace_events(trace_path)
    validate_trace_file(trace_path)

    assert [event.event_index for event in events] == [0, 1]


def test_validate_trace_events_rejects_nonsequential_indices() -> None:
    events = [
        TraceEvent(
            schema_version=TRACE_SCHEMA_VERSION,
            event_index=1,
            timestamp_utc="2026-06-20T00:00:00Z",
            event_type="replay_started",
            provenance_config=ReplayTraceProvenance(replay_run_id="replay_run_001"),
        )
    ]

    with pytest.raises(ValueError, match="Trace event index mismatch"):
        validate_trace_events(events)


def test_trace_event_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "typo_event",
                "provenance_config": {"replay_run_id": "replay_run_001"},
            }
        )


def test_trace_event_rejects_unknown_provenance_key() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "attempt_started",
                "provenance_config": {
                    "scorer_attempt_id": "scorer_attempt_001",
                    "task_id": "task_001",
                    "surprise": "not_allowed",
                },
            }
        )


def test_trace_event_rejects_wrong_provenance_family() -> None:
    with pytest.raises(ValidationError, match="requires replay trace provenance"):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "replay_started",
                "provenance_config": {
                    "scorer_attempt_id": "scorer_attempt_001",
                    "task_id": "task_001",
                },
            }
        )


def test_eval_event_rejects_wrong_provenance_family() -> None:
    with pytest.raises(ValidationError, match="requires eval trace provenance"):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_started",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                },
            }
        )


def test_command_finished_requires_command_provenance() -> None:
    with pytest.raises(
        ValidationError,
        match="command_finished provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "command_finished",
                "provenance_config": {
                    "scorer_attempt_id": "scorer_attempt_001",
                    "task_id": "task_001",
                },
            }
        )


def test_eval_attempt_finished_requires_child_attempt_id() -> None:
    with pytest.raises(
        ValidationError,
        match="eval_attempt_finished provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_attempt_finished",
                "provenance_config": {
                    "eval_run_id": "eval_run_001",
                    "config_hash": "xxh64:abc123",
                    "config_name": "scorer_control_policies",
                    "policy": "oracle",
                    "task_id": "toy_python_fix_001",
                    "task_index": 0,
                    "attempt_index": 0,
                    "eval_attempt_id": "eval_attempt_001",
                },
            }
        )


def test_eval_attempt_started_requires_eval_attempt_id() -> None:
    with pytest.raises(
        ValidationError,
        match="eval_attempt_started provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_attempt_started",
                "provenance_config": {
                    "eval_run_id": "eval_run_001",
                    "config_hash": "xxh64:abc123",
                    "config_name": "scorer_control_policies",
                    "policy": "oracle",
                    "task_id": "toy_python_fix_001",
                    "task_index": 0,
                    "attempt_index": 0,
                },
            }
        )


def test_eval_attempt_finished_accepts_agent_attempt_with_nested_scorer_id() -> None:
    event = TraceEvent.model_validate(
        {
            "schema_version": TRACE_SCHEMA_VERSION,
            "event_index": 0,
            "timestamp_utc": "2026-06-20T00:00:00Z",
            "event_type": "eval_attempt_finished",
            "provenance_config": {
                "eval_run_id": "eval_run_001",
                "config_hash": "xxh64:abc123",
                "config_name": "agent_control_policies",
                "policy": "agent-happy",
                "task_id": "toy_python_fix_001",
                "task_index": 0,
                "attempt_index": 0,
                "eval_attempt_id": "eval_attempt_001",
                "scorer_attempt_id": "scorer_attempt_001",
                "agent_attempt_id": "agent_attempt_001",
            },
        }
    )

    provenance = event.provenance_config
    assert isinstance(provenance, EvalTraceProvenance)
    assert provenance.agent_attempt_id == "agent_attempt_001"
    assert provenance.scorer_attempt_id == "scorer_attempt_001"


def test_scored_agent_eval_attempt_payload_requires_nested_scorer_id() -> None:
    with pytest.raises(
        ValidationError,
        match="eval_attempt_finished provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_attempt_finished",
                "provenance_config": {
                    "eval_run_id": "eval_run_001",
                    "config_hash": "xxh64:abc123",
                    "config_name": "agent_control_policies",
                    "policy": "agent-happy",
                    "task_id": "toy_python_fix_001",
                    "task_index": 0,
                    "attempt_index": 0,
                    "eval_attempt_id": "eval_attempt_001",
                    "agent_attempt_id": "agent_attempt_001",
                },
                "output_payload": {
                    "artifact_type": "agent_attempt",
                    "agent": {
                        "scorer_attempt": {
                            "scorer_attempt_id": "scorer_attempt_001",
                            "status": "PASS",
                        }
                    },
                },
            }
        )


def test_scored_agent_eval_attempt_payload_requires_nested_scorer_payload_id() -> None:
    with pytest.raises(
        ValidationError,
        match="agent scorer_attempt payload requires scorer_attempt_id",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_attempt_finished",
                "provenance_config": {
                    "eval_run_id": "eval_run_001",
                    "config_hash": "xxh64:abc123",
                    "config_name": "agent_control_policies",
                    "policy": "agent-happy",
                    "task_id": "toy_python_fix_001",
                    "task_index": 0,
                    "attempt_index": 0,
                    "eval_attempt_id": "eval_attempt_001",
                    "agent_attempt_id": "agent_attempt_001",
                    "scorer_attempt_id": "scorer_attempt_001",
                },
                "output_payload": {
                    "artifact_type": "agent_attempt",
                    "agent": {
                        "scorer_attempt": {
                            "status": "PASS",
                        }
                    },
                },
            }
        )


def test_scored_agent_eval_attempt_payload_requires_nested_scorer_payload() -> None:
    with pytest.raises(
        ValidationError,
        match="scored agent attempt payload requires agent.scorer_attempt",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_attempt_finished",
                "provenance_config": {
                    "eval_run_id": "eval_run_001",
                    "config_hash": "xxh64:abc123",
                    "config_name": "agent_control_policies",
                    "policy": "agent-happy",
                    "task_id": "toy_python_fix_001",
                    "task_index": 0,
                    "attempt_index": 0,
                    "eval_attempt_id": "eval_attempt_001",
                    "agent_attempt_id": "agent_attempt_001",
                    "scorer_attempt_id": "scorer_attempt_001",
                },
                "output_payload": {
                    "artifact_type": "agent_attempt",
                    "agent": {
                        "status": "scored",
                    },
                },
            }
        )


def test_scored_agent_eval_attempt_payload_requires_matching_scorer_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="provenance.scorer_attempt_id must match",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_attempt_finished",
                "provenance_config": {
                    "eval_run_id": "eval_run_001",
                    "config_hash": "xxh64:abc123",
                    "config_name": "agent_control_policies",
                    "policy": "agent-happy",
                    "task_id": "toy_python_fix_001",
                    "task_index": 0,
                    "attempt_index": 0,
                    "eval_attempt_id": "eval_attempt_001",
                    "agent_attempt_id": "agent_attempt_001",
                    "scorer_attempt_id": "scorer_attempt_001",
                },
                "output_payload": {
                    "artifact_type": "agent_attempt",
                    "agent": {
                        "scorer_attempt": {
                            "scorer_attempt_id": "scorer_attempt_002",
                            "status": "PASS",
                        }
                    },
                },
            }
        )


def test_scorer_eval_attempt_payload_rejects_agent_attempt_id() -> None:
    with pytest.raises(
        ValidationError,
        match="scorer eval attempt payload cannot include agent_attempt_id",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "eval_attempt_finished",
                "provenance_config": {
                    "eval_run_id": "eval_run_001",
                    "config_hash": "xxh64:abc123",
                    "config_name": "scorer_control_policies",
                    "policy": "oracle",
                    "task_id": "toy_python_fix_001",
                    "task_index": 0,
                    "attempt_index": 0,
                    "eval_attempt_id": "eval_attempt_001",
                    "scorer_attempt_id": "scorer_attempt_001",
                    "agent_attempt_id": "agent_attempt_001",
                },
                "output_payload": {
                    "artifact_type": "scorer_attempt",
                    "scorer": {
                        "scorer_attempt_id": "scorer_attempt_001",
                        "status": "PASS",
                    },
                },
            }
        )


def test_replay_provenance_rejects_generic_attempt_ids() -> None:
    for generic_field in (
        "source_artifact_id",
        "replay_artifact_id",
        "source_attempt_id",
        "replay_attempt_id",
    ):
        with pytest.raises(ValidationError):
            ReplayTraceProvenance.model_validate(
                {
                    "replay_run_id": "replay_run_001",
                    generic_field: "attempt_001",
                }
            )


def test_replay_provenance_rejects_legacy_replay_id() -> None:
    with pytest.raises(ValidationError):
        ReplayTraceProvenance.model_validate({"replay_id": "replay_001"})


def test_replay_attempt_event_requires_source_attempt_provenance() -> None:
    with pytest.raises(
        ValidationError,
        match="source_attempt_loaded provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "source_attempt_loaded",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                    "source_eval_run_id": "eval_run_001",
                },
            }
        )


def test_source_manifest_loaded_rejects_scorer_attempt_source_id() -> None:
    with pytest.raises(
        ValidationError,
        match="source_manifest_loaded provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "source_manifest_loaded",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                    "source_scorer_attempt_id": "scorer_attempt_001",
                },
            }
        )


def test_source_manifest_loaded_forbids_attempt_level_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="source_manifest_loaded provenance forbids field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "source_manifest_loaded",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                    "source_eval_run_id": "eval_run_001",
                    "source_scorer_attempt_id": "scorer_attempt_001",
                },
            }
        )


def test_source_manifest_loaded_rejects_multiple_source_families() -> None:
    with pytest.raises(
        ValidationError,
        match="source_manifest_loaded provenance must include exactly one",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "source_manifest_loaded",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                    "source_eval_run_id": "eval_run_001",
                    "source_agent_attempt_id": "agent_attempt_001",
                },
            }
        )


def test_eval_run_sourced_replay_attempt_requires_source_eval_attempt_id() -> None:
    with pytest.raises(
        ValidationError,
        match="source_attempt_loaded provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "source_attempt_loaded",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                    "source_eval_run_id": "eval_run_001",
                    "task_id": "toy_python_fix_001",
                    "source_scorer_attempt_id": "scorer_attempt_001",
                },
            }
        )


def test_replay_finished_rejects_mismatched_source_and_replayed_id_types() -> None:
    with pytest.raises(
        ValidationError,
        match="source_scorer_attempt_id requires replayed_scorer_attempt_id",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "fresh_attempt_finished",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                    "task_id": "toy_python_fix_001",
                    "source_scorer_attempt_id": "scorer_attempt_001",
                    "replayed_agent_attempt_id": "agent_attempt_001",
                },
            }
        )


def test_replay_finished_rejects_multiple_source_and_replayed_id_families() -> None:
    with pytest.raises(
        ValidationError,
        match="exactly one complete source/replayed attempt id family",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "comparison_recorded",
                "provenance_config": {
                    "replay_run_id": "replay_run_001",
                    "task_id": "toy_python_fix_001",
                    "source_scorer_attempt_id": "scorer_attempt_001",
                    "replayed_scorer_attempt_id": "scorer_attempt_002",
                    "source_agent_attempt_id": "agent_attempt_001",
                    "replayed_agent_attempt_id": "agent_attempt_002",
                },
            }
        )
