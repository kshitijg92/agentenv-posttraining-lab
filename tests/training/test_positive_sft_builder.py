import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pytest

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION,
    load_positive_sft_export_manifest,
    load_positive_sft_training_materialization_manifest,
    load_trajectory_export_manifest,
)
from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.candidates.export import (
    export_training_candidate_records,
)
from agentenv.training.positive_sft.builder import build_positive_sft_examples
from agentenv.training.positive_sft.export import (
    export_positive_sft_examples,
    load_positive_sft_export_artifact,
)
import agentenv.training.positive_sft.materialization.export as materialization_export_module
from agentenv.training.positive_sft.materialization.export import (
    export_positive_sft_training_materializations,
    load_positive_sft_training_materialization_artifact,
)
from agentenv.training.positive_sft.review import (
    build_positive_sft_review_selections,
    initialize_positive_sft_review_artifact,
    validate_positive_sft_review_artifact,
    write_positive_sft_review_records_jsonl,
)
from agentenv.training.positive_sft.schema import (
    POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION,
)
from agentenv.trajectories.export import (
    export_trajectory_records_from_eval_artifact,
    hash_file,
    write_trajectory_records_jsonl,
)
from agentenv.trajectories.review import (
    TrajectoryReviewArtifact,
    initialize_trajectory_review_artifact,
    write_trajectory_review_records_jsonl,
)
from agentenv.trajectories.schema import (
    ArtifactRef,
    ReviewDecision,
    TrajectoryRecord,
)


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
MODEL_INPUT_PROTOCOL = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)


def test_build_positive_sft_examples_from_training_candidate_export(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    examples = build_positive_sft_examples(
        candidate_export_dir,
        positive_sft_review_dir=sft_review.out_dir,
    )

    assert len(examples) == 1
    example = examples[0]
    assert example.example_id.startswith("positive_sft_example_")
    assert example.provenance_ids.trajectory_id.startswith("trajectory_")
    assert example.provenance_ids.eval_attempt_id.startswith("eval_attempt_")
    assert example.provenance_ids.agent_attempt_id.startswith("agent_attempt_")
    assert example.provenance_ids.task_id == "toy_python_fix_001"
    assert example.provenance_ids.policy_id == "local-model"
    assert example.prompt_provenance.prompt_builder_version == (
        "agent_task_initial_prompt_builder_v0"
    )
    assert example.prompt_provenance.prompt_builder_code_hash.startswith("xxh64:")
    assert example.source_provenance.source_type == "original"
    assert (
        example.source_provenance.task_outcome_provenance
        == "executed_source_trajectory"
    )
    assert example.source_provenance.source_artifact_ref.content_hash is not None
    assert example.task_input.task_id == "toy_python_fix_001"
    assert [message.role for message in example.messages[:2]] == ["system", "user"]
    assert any(message.role == "assistant" for message in example.messages)
    assert "metadata" not in example.messages[0].model_dump(mode="json")
    assert "final_patch" not in example.model_dump(mode="json")


def test_build_positive_sft_examples_skips_non_positive_candidates(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_control_training_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    examples = build_positive_sft_examples(
        candidate_export_dir,
        positive_sft_review_dir=sft_review.out_dir,
    )

    assert examples == ()


def test_positive_sft_materializes_only_human_approved_prefix(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    validation = validate_positive_sft_review_artifact(artifact.out_dir)
    selections = build_positive_sft_review_selections(
        validation.source_candidate_export,
        repair_validation=None,
        selected_repair_ids=(),
    )
    source_messages = selections[0].messages
    first_assistant = next(
        message for message in source_messages if message.role == "assistant"
    )
    accepted = artifact.reviews[0].model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "positive_sft_review_0001",
            "reviewer_id": "reviewer",
            "review_decision": "accepted",
            "last_approved_assistant_message_id": first_assistant.message_id,
        }
    )
    write_positive_sft_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        (accepted,),
    )

    examples = build_positive_sft_examples(
        candidate_export_dir,
        positive_sft_review_dir=artifact.out_dir,
    )

    assert len(examples) == 1
    example = examples[0]
    assert example.messages[-1].message_id == first_assistant.message_id
    assert example.messages[-1].role == "assistant"
    assert len(example.messages) < len(source_messages)
    assert example.review_provenance.last_approved_assistant_message_id == (
        first_assistant.message_id
    )


def test_positive_sft_reload_rejects_prefix_review_drift(tmp_path: Path) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )
    reviews_path = sft_review.out_dir / sft_review.manifest.artifacts["reviews"]
    reviews_path.write_text(reviews_path.read_text() + "\n")

    with pytest.raises(ValueError, match="source reviews JSONL hash mismatch"):
        load_positive_sft_export_artifact(export.out_dir)


def test_build_positive_sft_examples_rejects_source_trajectory_jsonl_drift(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    manifest = json.loads((candidate_export_dir / MANIFEST_FILENAME).read_text())
    trajectory_export_dir = Path(manifest["source_trajectory_export_dir"])
    trajectories_path = trajectory_export_dir / "trajectories.jsonl"
    trajectories_path.write_text(trajectories_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Trajectory JSONL hash mismatch"):
        build_positive_sft_examples(
            candidate_export_dir,
            positive_sft_review_dir=sft_review.out_dir,
        )


def test_build_positive_sft_examples_rejects_source_review_jsonl_drift(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    manifest = json.loads((candidate_export_dir / MANIFEST_FILENAME).read_text())
    review_dir = Path(manifest["source_review_dir"])
    reviews_path = review_dir / "reviews.jsonl"
    reviews_path.write_text(reviews_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Source reviews JSONL hash mismatch"):
        build_positive_sft_examples(
            candidate_export_dir,
            positive_sft_review_dir=sft_review.out_dir,
        )


def test_build_positive_sft_examples_rejects_prompt_loop_artifact_hash_mismatch(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    manifest = json.loads((candidate_export_dir / MANIFEST_FILENAME).read_text())
    trajectory_export_dir = Path(manifest["source_trajectory_export_dir"])
    record = load_trajectory_record(trajectory_export_dir)
    prompt_loop_path = (
        Path(record.artifacts.eval_run_path) / require_prompt_loop_ref(record).path
    )
    prompt_loop_path.write_text(prompt_loop_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        build_positive_sft_examples(
            candidate_export_dir,
            positive_sft_review_dir=sft_review.out_dir,
        )


def test_build_positive_sft_examples_rejects_leaked_sft_payload(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(
        tmp_path,
        leak_prompt_loop=True,
    )
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    with pytest.raises(
        ValueError,
        match="Positive SFT example record failed leakage scan",
    ):
        build_positive_sft_examples(
            candidate_export_dir,
            positive_sft_review_dir=sft_review.out_dir,
        )


def test_build_positive_sft_examples_scans_full_record_not_only_messages(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(
        tmp_path,
        leak_prompt_provenance=True,
    )
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    with pytest.raises(
        ValueError,
        match="Positive SFT example record failed leakage scan",
    ):
        build_positive_sft_examples(
            candidate_export_dir,
            positive_sft_review_dir=sft_review.out_dir,
        )


def test_export_positive_sft_examples_writes_manifest_and_jsonl(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )

    manifest = load_positive_sft_export_manifest(export.out_dir / MANIFEST_FILENAME)
    assert manifest.artifact_type == "positive_sft_export"
    assert (
        manifest.artifact_schema_version == POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION
    )
    assert manifest.source_positive_sft_review.artifact_dir == str(
        sft_review.out_dir.resolve()
    )
    assert manifest.source_positive_sft_review.manifest_hash.startswith("xxh64:")
    assert manifest.source_positive_sft_review.reviews_jsonl_hash.startswith("xxh64:")
    assert (
        manifest.positive_sft_example_record_schema_version
        == POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
    )
    assert manifest.record_count == 1
    assert manifest.original_record_count == 1
    assert manifest.repaired_record_count == 0
    assert manifest.positive_sft_examples_jsonl_hash.startswith("xxh64:")
    assert manifest.training_authorization == "not_authorized"
    assert manifest.artifacts == {
        "positive_sft_examples": "positive_sft_examples.jsonl",
    }
    assert len(export.records) == 1
    assert (
        export.records[0].schema_version == POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
    )
    assert (export.out_dir / "positive_sft_examples.jsonl").is_file()


def test_export_positive_sft_examples_allows_empty_export(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_control_training_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )

    assert export.manifest.record_count == 0
    assert export.manifest.original_record_count == 0
    assert export.manifest.repaired_record_count == 0
    assert export.records == ()
    assert (export.out_dir / "positive_sft_examples.jsonl").read_text() == ""


def test_load_positive_sft_export_rejects_jsonl_hash_mismatch(
    tmp_path: Path,
) -> None:
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )
    examples_path = export.out_dir / export.manifest.artifacts["positive_sft_examples"]
    examples_path.write_text(examples_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Positive SFT examples JSONL hash mismatch"):
        load_positive_sft_export_artifact(export.out_dir)


def test_export_positive_sft_training_materializations_persists_accounted_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positive_sft_export = build_positive_sft_export(tmp_path)
    install_character_tokenizer(monkeypatch)

    export = export_positive_sft_training_materializations(
        positive_sft_export.out_dir,
        MODEL_INPUT_PROTOCOL,
        tmp_path / "positive-sft-training-materialization",
        max_sequence_length=10_000,
    )

    manifest = load_positive_sft_training_materialization_manifest(
        export.out_dir / MANIFEST_FILENAME
    )
    assert manifest.artifact_type == "positive_sft_training_materialization"
    assert manifest.training_authorization == "not_authorized"
    assert manifest.record_count == positive_sft_export.manifest.record_count == 1
    assert manifest.completed_count == 1
    assert manifest.failed_count == 0
    assert manifest.sequence_length_exceeded_count == 0
    assert manifest.materialization_error_count == 0
    assert manifest.model_input_protocol_id == (
        "qwen2_5_coder_3b_agentenv_json"
    )
    assert manifest.model_input_protocol_hash == hash_file(MODEL_INPUT_PROTOCOL)
    assert manifest.max_sequence_length == 10_000
    assert manifest.materializations_jsonl_hash.startswith("xxh64:")
    assert manifest.artifacts == {"materializations": "materializations.jsonl"}
    assert len(export.records) == 1
    assert export.records[0].status == "completed"
    assert (export.out_dir / "materializations.jsonl").is_file()


def test_materialization_export_counts_overlength_without_dropping_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positive_sft_export = build_positive_sft_export(tmp_path)
    install_character_tokenizer(monkeypatch)

    export = export_positive_sft_training_materializations(
        positive_sft_export.out_dir,
        MODEL_INPUT_PROTOCOL,
        tmp_path / "positive-sft-training-materialization",
        max_sequence_length=1,
    )

    assert export.manifest.record_count == 1
    assert export.manifest.completed_count == 0
    assert export.manifest.failed_count == 1
    assert export.manifest.sequence_length_exceeded_count == 1
    assert export.manifest.materialization_error_count == 0
    assert len(export.records) == positive_sft_export.manifest.record_count
    assert export.records[0].status == "failed"
    assert export.records[0].failure_kind == "sequence_length_exceeded"


def test_materialization_reload_rejects_source_identity_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = build_positive_sft_training_materialization_export(
        tmp_path,
        monkeypatch,
    )
    records_path = export.out_dir / "materializations.jsonl"
    payload = json.loads(records_path.read_text())
    payload["source_positive_sft_example_id"] = "substituted_example"
    records_path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    rewrite_materialization_manifest_jsonl_hash(export.out_dir)

    with pytest.raises(ValueError, match="source order/id mismatch"):
        load_positive_sft_training_materialization_artifact(export.out_dir)


def test_materialization_reload_rebuilds_and_rejects_label_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = build_positive_sft_training_materialization_export(
        tmp_path,
        monkeypatch,
    )
    records_path = export.out_dir / "materializations.jsonl"
    payload = json.loads(records_path.read_text())
    supervised_index = next(
        index for index, label in enumerate(payload["labels"]) if label != -100
    )
    payload["labels"][supervised_index] = -100
    payload["supervised_token_count"] -= 1
    payload["ignored_token_count"] += 1
    records_path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    rewrite_materialization_manifest_jsonl_hash(export.out_dir)

    with pytest.raises(ValueError, match="do not match records rebuilt"):
        load_positive_sft_training_materialization_artifact(export.out_dir)


def test_materialization_reload_rejects_jsonl_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = build_positive_sft_training_materialization_export(
        tmp_path,
        monkeypatch,
    )
    records_path = export.out_dir / "materializations.jsonl"
    records_path.write_text(records_path.read_text() + "\n")

    with pytest.raises(ValueError, match="materializations JSONL hash mismatch"):
        load_positive_sft_training_materialization_artifact(export.out_dir)


def initialize_accepted_positive_sft_review(
    candidate_export_dir: Path,
    out_dir: Path,
):
    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        out_dir,
    )
    validation = validate_positive_sft_review_artifact(artifact.out_dir)
    selections = build_positive_sft_review_selections(
        validation.source_candidate_export,
        repair_validation=None,
        selected_repair_ids=(),
    )
    selection_by_candidate = {
        selection.candidate_hash: selection for selection in selections
    }
    accepted = tuple(
        review.model_copy(
            update={
                "review_status": "reviewed",
                "review_id": f"positive_sft_review_{index:04d}",
                "reviewer_id": "reviewer",
                "review_decision": "accepted",
                "last_approved_assistant_message_id": next(
                    message.message_id
                    for message in reversed(
                        selection_by_candidate[
                            review.source_training_candidate_record_hash
                        ].messages
                    )
                    if message.role == "assistant"
                ),
            }
        )
        for index, review in enumerate(artifact.reviews, start=1)
    )
    write_positive_sft_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        accepted,
    )
    return artifact


def build_positive_sft_export(tmp_path: Path):
    candidate_export_dir = build_positive_sft_candidate_export(tmp_path)
    sft_review = initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    return export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )


def build_positive_sft_training_materialization_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    positive_sft_export = build_positive_sft_export(tmp_path)
    install_character_tokenizer(monkeypatch)
    return export_positive_sft_training_materializations(
        positive_sft_export.out_dir,
        MODEL_INPUT_PROTOCOL,
        tmp_path / "positive-sft-training-materialization",
        max_sequence_length=10_000,
    )


def install_character_tokenizer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        materialization_export_module,
        "load_pinned_tokenizer",
        lambda *args, **kwargs: _CharacterMaterializationTokenizer(),
    )


def rewrite_materialization_manifest_jsonl_hash(export_dir: Path) -> None:
    manifest_path = export_dir / MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text())
    payload["materializations_jsonl_hash"] = hash_file(
        export_dir / "materializations.jsonl"
    )
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


@dataclass
class _CharacterTokenizerBackend:
    normalizer: Any = None


class _CharacterMaterializationTokenizer:
    is_fast = True
    backend_tokenizer = _CharacterTokenizerBackend()

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        return_offsets_mapping: bool,
    ) -> dict[str, object]:
        return {
            "input_ids": [ord(character) for character in text],
            "offset_mapping": [
                (character_index, character_index + 1)
                for character_index in range(len(text))
            ],
        }

    def decode(
        self,
        token_ids: Sequence[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        return "".join(chr(token_id) for token_id in token_ids)


def build_positive_sft_candidate_export(
    tmp_path: Path,
    *,
    leak_prompt_loop: bool = False,
    leak_prompt_provenance: bool = False,
) -> Path:
    trajectory_export_dir = build_agent_model_trajectory_export(
        tmp_path,
        leak_prompt_loop=leak_prompt_loop,
        leak_prompt_provenance=leak_prompt_provenance,
    )
    review_artifact = initialize_trajectory_review_artifact(
        trajectory_export_dir,
        tmp_path / "trajectory-review",
    )
    write_single_review_decision(review_artifact, "accepted")
    candidate_export = export_training_candidate_records(
        trajectory_export_dir,
        review_artifact.out_dir,
        tmp_path / "training-candidates",
    )
    return candidate_export.out_dir


def build_control_training_candidate_export(tmp_path: Path) -> Path:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "eval-run",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        tmp_path / "trajectory-export",
    )
    review_artifact = initialize_trajectory_review_artifact(
        trajectory_export.out_dir,
        tmp_path / "trajectory-review",
    )
    write_single_review_decision(review_artifact, "accepted")
    candidate_export = export_training_candidate_records(
        trajectory_export.out_dir,
        review_artifact.out_dir,
        tmp_path / "training-candidates",
    )
    return candidate_export.out_dir


def build_agent_model_trajectory_export(
    tmp_path: Path,
    *,
    leak_prompt_loop: bool,
    leak_prompt_provenance: bool,
) -> Path:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "eval-run",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        tmp_path / "trajectory-export",
    )
    record = build_agent_model_trajectory_record(trajectory_export.records[0])
    if leak_prompt_loop:
        record = leak_prompt_loop_artifact(record)
    if leak_prompt_provenance:
        record = leak_prompt_provenance_artifact(record)
    rewrite_trajectory_export_records(trajectory_export.out_dir, (record,))
    return trajectory_export.out_dir


def write_single_review_decision(
    review_artifact: TrajectoryReviewArtifact,
    decision: ReviewDecision,
) -> None:
    review = review_artifact.reviews[0].model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "kshitij",
            "review_decision": decision,
        }
    )
    write_trajectory_review_records_jsonl(
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"],
        (review,),
    )


def build_agent_model_trajectory_record(
    trajectory: TrajectoryRecord,
) -> TrajectoryRecord:
    payload = trajectory.model_dump(mode="json")
    payload["identity"]["policy_id"] = "local-model"
    payload["policy"] = {
        "policy_id": "local-model",
        "policy_name": "local-model",
        "policy_spec": {
            "type": AGENT_MODEL_POLICY_TYPE,
            "model_config": "configs/models/local_model.yaml",
            "decoding_config": "configs/decoding/local_model.yaml",
            "attempts": 1,
            "replay": {"repeats": 0},
        },
    }
    return type(trajectory).model_validate(payload)


def leak_prompt_loop_artifact(
    trajectory: TrajectoryRecord,
) -> TrajectoryRecord:
    prompt_loop_ref = require_prompt_loop_ref(trajectory)
    prompt_loop_path = Path(trajectory.artifacts.eval_run_path) / prompt_loop_ref.path
    payload = json.loads(prompt_loop_path.read_text())
    payload["messages"][1]["content"] += "\nhidden_tests"
    prompt_loop_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    record_payload = trajectory.model_dump(mode="json")
    record_payload["artifacts"]["prompt_loop_result_json"]["content_hash"] = hash_file(
        prompt_loop_path
    )
    return type(trajectory).model_validate(record_payload)


def leak_prompt_provenance_artifact(
    trajectory: TrajectoryRecord,
) -> TrajectoryRecord:
    prompt_loop_ref = require_prompt_loop_ref(trajectory)
    prompt_loop_path = Path(trajectory.artifacts.eval_run_path) / prompt_loop_ref.path
    payload = json.loads(prompt_loop_path.read_text())
    payload["prompt_builder_version"] += "_hidden_tests"
    prompt_loop_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    record_payload = trajectory.model_dump(mode="json")
    record_payload["artifacts"]["prompt_loop_result_json"]["content_hash"] = hash_file(
        prompt_loop_path
    )
    return type(trajectory).model_validate(record_payload)


def require_prompt_loop_ref(trajectory: TrajectoryRecord) -> ArtifactRef:
    prompt_loop_ref = trajectory.artifacts.prompt_loop_result_json
    if prompt_loop_ref is None:
        raise AssertionError("expected prompt_loop_result_json")
    return prompt_loop_ref


def rewrite_trajectory_export_records(
    trajectory_export_dir: Path,
    records: tuple[TrajectoryRecord, ...],
) -> None:
    trajectories_path = trajectory_export_dir / "trajectories.jsonl"
    write_trajectory_records_jsonl(trajectories_path, list(records))
    manifest = load_trajectory_export_manifest(
        trajectory_export_dir / MANIFEST_FILENAME
    )
    updated_manifest = manifest.model_copy(
        update={
            "record_count": len(records),
            "trajectories_jsonl_hash": hash_file(trajectories_path),
        }
    )
    (trajectory_export_dir / MANIFEST_FILENAME).write_text(
        json.dumps(
            updated_manifest.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def load_trajectory_record(trajectory_export_dir: Path) -> TrajectoryRecord:
    trajectories_path = trajectory_export_dir / "trajectories.jsonl"
    payload = json.loads(trajectories_path.read_text().splitlines()[0])
    return TrajectoryRecord.model_validate(payload)
