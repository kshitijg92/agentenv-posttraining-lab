import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, cast

import pytest

import agentenv.training.preferences.materialization.export as export_module
from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    PREFERENCE_PAIR_EXPORT_ARTIFACT_REFS,
    PREFERENCE_PAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
    PreferencePairExportManifest,
    load_dpo_training_materialization_manifest,
)
from agentenv.hashing import hash_file
from agentenv.models.schema import MessageWithoutMetadata
from agentenv.training.preferences.hashing import build_preference_pair_id
from agentenv.training.preferences.materialization.export import (
    export_dpo_training_materializations,
    load_dpo_training_materialization_artifact,
)
from agentenv.training.preferences.materialization.source_reconstruction import (
    DPOPreferencePairMaterializationInput,
)
from agentenv.training.preferences.pair_export import PreferencePairExport
from agentenv.training.preferences.schema import (
    PREFERENCE_PAIR_RECORD_SCHEMA_VERSION,
    PreferencePairRecord,
)


PROTOCOL_PATH = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)


@dataclass
class _BackendTokenizer:
    normalizer: Any = None


class _CharacterTokenizer:
    is_fast = True

    def __init__(self) -> None:
        self.backend_tokenizer = _BackendTokenizer()

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


def test_dpo_materialization_export_persists_one_accounted_result_per_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export, _ = _install_source_pair_export(tmp_path, monkeypatch)

    export = export_dpo_training_materializations(
        source_export.out_dir,
        PROTOCOL_PATH,
        tmp_path / "dpo-materialization",
        max_sequence_length=10_000,
    )

    manifest = load_dpo_training_materialization_manifest(
        export.out_dir / MANIFEST_FILENAME
    )
    assert manifest.artifact_type == "dpo_training_materialization"
    assert manifest.training_authorization == "not_authorized"
    assert manifest.record_count == source_export.manifest.record_count == 1
    assert manifest.completed_count == 1
    assert manifest.failed_count == 0
    assert manifest.sequence_length_exceeded_count == 0
    assert manifest.materialization_error_count == 0
    assert manifest.model_input_protocol_id == "qwen2_5_coder_3b_agentenv_json"
    assert manifest.model_input_protocol_hash == hash_file(PROTOCOL_PATH)
    assert manifest.max_sequence_length == 10_000
    assert manifest.artifacts == {"materializations": "materializations.jsonl"}
    assert len(export.records) == 1
    assert export.records[0].status == "completed"


def test_dpo_materialization_export_preserves_atomic_overlength_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export, _ = _install_source_pair_export(tmp_path, monkeypatch)

    export = export_dpo_training_materializations(
        source_export.out_dir,
        PROTOCOL_PATH,
        tmp_path / "dpo-materialization",
        max_sequence_length=1,
    )

    assert export.manifest.record_count == 1
    assert export.manifest.completed_count == 0
    assert export.manifest.failed_count == 1
    assert export.manifest.sequence_length_exceeded_count == 1
    assert export.records[0].status == "failed"
    assert export.records[0].failure_kind == "sequence_length_exceeded"


def test_dpo_materialization_export_allows_an_accounted_empty_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export, _ = _install_source_pair_export(
        tmp_path,
        monkeypatch,
        include_pair=False,
    )

    export = export_dpo_training_materializations(
        source_export.out_dir,
        PROTOCOL_PATH,
        tmp_path / "dpo-materialization",
        max_sequence_length=10_000,
    )

    assert export.records == ()
    assert export.manifest.record_count == 0
    assert export.manifest.completed_count == 0
    assert export.manifest.failed_count == 0


def test_dpo_materialization_reload_rebuilds_and_rejects_token_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _build_materialization_export(tmp_path, monkeypatch)
    records_path = export.out_dir / "materializations.jsonl"
    payload = json.loads(records_path.read_text())
    response_index = payload["shared_prompt_token_count"]
    payload["chosen_input_ids"][response_index] += 1
    payload["chosen_labels"][response_index] += 1
    records_path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    _rewrite_materialization_manifest_hash(export.out_dir)

    with pytest.raises(ValueError, match="do not match records rebuilt"):
        load_dpo_training_materialization_artifact(export.out_dir)


def test_dpo_materialization_reload_rejects_source_pair_payload_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export, _ = _install_source_pair_export(tmp_path, monkeypatch)
    export = export_dpo_training_materializations(
        source_export.out_dir,
        PROTOCOL_PATH,
        tmp_path / "dpo-materialization",
        max_sequence_length=10_000,
    )
    source_pairs_path = (
        source_export.out_dir / source_export.manifest.artifacts["preference_pairs"]
    )
    source_pairs_path.write_text(source_pairs_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Source preference-pair JSONL hash mismatch"):
        load_dpo_training_materialization_artifact(export.out_dir)


def _build_materialization_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_export, _ = _install_source_pair_export(tmp_path, monkeypatch)
    return export_dpo_training_materializations(
        source_export.out_dir,
        PROTOCOL_PATH,
        tmp_path / "dpo-materialization",
        max_sequence_length=10_000,
    )


def _install_source_pair_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_pair: bool = True,
) -> tuple[PreferencePairExport, tuple[DPOPreferencePairMaterializationInput, ...]]:
    source_dir = tmp_path / "preference-pairs"
    source_dir.mkdir()
    materialization_inputs = (_pair_input(),) if include_pair else ()
    pairs = tuple(item.source_pair for item in materialization_inputs)
    pairs_path = source_dir / PREFERENCE_PAIR_EXPORT_ARTIFACT_REFS["preference_pairs"]
    pairs_path.write_text(
        "".join(
            json.dumps(pair.model_dump(mode="json"), sort_keys=True) + "\n"
            for pair in pairs
        )
    )
    manifest = PreferencePairExportManifest.model_validate(
        {
            "artifact_type": "preference_pair_export",
            "artifact_schema_version": PREFERENCE_PAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "created_at": "2026-07-21T20:00:00Z",
            "source_preference_comparison_export": {
                "artifact_dir": "comparison-source",
                "manifest_hash": "xxh64:1111111111111111",
                "comparison_candidates_jsonl_hash": "xxh64:2222222222222222",
            },
            "source_preference_adjudication_review": {
                "artifact_dir": "review-source",
                "manifest_hash": "xxh64:3333333333333333",
                "adjudications_jsonl_hash": "xxh64:4444444444444444",
            },
            "training_authorization": "not_authorized",
            "preference_pair_record_schema_version": (
                PREFERENCE_PAIR_RECORD_SCHEMA_VERSION
            ),
            "source_adjudication_record_count": len(pairs),
            "source_not_reviewed_count": 0,
            "source_preferred_count": len(pairs),
            "source_tie_count": 0,
            "source_ambiguous_count": 0,
            "source_invalid_count": 0,
            "record_count": len(pairs),
            "shared_context_count": len(pairs),
            "preference_pairs_jsonl_hash": hash_file(pairs_path),
            "artifacts": dict(PREFERENCE_PAIR_EXPORT_ARTIFACT_REFS),
        }
    )
    (source_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    source_export = PreferencePairExport(
        out_dir=source_dir.resolve(),
        manifest=manifest,
        records=pairs,
        source_comparison_export=cast(Any, None),
        source_adjudication_review=cast(Any, None),
    )
    monkeypatch.setattr(
        export_module,
        "load_preference_pair_export_artifact",
        lambda _path: source_export,
    )
    monkeypatch.setattr(
        export_module,
        "reconstruct_dpo_preference_pair_inputs",
        lambda _source: materialization_inputs,
    )
    monkeypatch.setattr(
        export_module,
        "load_pinned_tokenizer",
        lambda *args, **kwargs: _CharacterTokenizer(),
    )
    return source_export, materialization_inputs


def _pair_input() -> DPOPreferencePairMaterializationInput:
    comparison_candidate_id = "preference_comparison_fixture"
    comparison_hash = "xxh64:5555555555555555"
    adjudication_hash = "xxh64:6666666666666666"
    pair = PreferencePairRecord.model_validate(
        {
            "preference_pair_id": build_preference_pair_id(
                comparison_candidate_id=comparison_candidate_id,
                source_preference_comparison_candidate_record_hash=comparison_hash,
                source_preference_adjudication_record_hash=adjudication_hash,
            ),
            "source": {
                "comparison_candidate_id": comparison_candidate_id,
                "source_preference_comparison_candidate_record_hash": (comparison_hash),
                "source_preference_adjudication_record_hash": adjudication_hash,
            },
        }
    )
    return DPOPreferencePairMaterializationInput(
        source_pair=pair,
        context_messages=(
            MessageWithoutMetadata(
                message_id="message_00000000000000000000000000000001",
                role="system",
                content="Use one JSON action per turn.",
            ),
            MessageWithoutMetadata(
                message_id="message_00000000000000000000000000000002",
                role="user",
                content="Inspect and fix the code.",
            ),
        ),
        chosen_action=MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000003",
            role="assistant",
            content='{"action":"final_answer","text":"done"}',
        ),
        rejected_action=MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000004",
            role="assistant",
            content='{"action":"tool_call","tool_name":"read_file"}',
        ),
    )


def _rewrite_materialization_manifest_hash(export_dir: Path) -> None:
    manifest_path = export_dir / MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text())
    payload["materializations_jsonl_hash"] = hash_file(
        export_dir / "materializations.jsonl"
    )
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
