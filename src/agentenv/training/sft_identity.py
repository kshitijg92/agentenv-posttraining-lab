from agentenv.hashing import hash_json


def build_positive_sft_example_id(
    *,
    source_type: str,
    source_training_candidate_record_hash: str,
    source_artifact_content_hash: str,
    source_training_candidate_repair_record_hash: str | None = None,
) -> str:
    identity_hash = hash_json(
        {
            "source_type": source_type,
            "source_training_candidate_record_hash": (
                source_training_candidate_record_hash
            ),
            "source_artifact_content_hash": source_artifact_content_hash,
            "source_training_candidate_repair_record_hash": (
                source_training_candidate_repair_record_hash
            ),
        }
    )
    return f"positive_sft_example_{identity_hash.removeprefix('xxh64:')}"
