from pathlib import Path

from agentenv.hashing import hash_file
from agentenv.training.preferences.schema import PreferenceRubricProvenance


RUBRIC_PATH = Path(
    "configs/training/preference_rubrics/overall_action_preference_v0.md"
)


def test_overall_action_preference_rubric_is_pinnable_and_matches_contract() -> None:
    content = RUBRIC_PATH.read_text()
    normalized_content = " ".join(content.split())
    content_hash = hash_file(RUBRIC_PATH)

    provenance = PreferenceRubricProvenance.model_validate(
        {
            "adjudication_scope": "overall_action_preference",
            "rubric_id": "overall_action_preference",
            "rubric_version": "overall_action_preference_v0",
            "rubric_ref": {
                "path": "rubrics/overall_action_preference_v0.md",
                "content_hash": content_hash,
            },
        }
    )

    assert provenance.rubric_ref.content_hash == content_hash
    assert "task success less likely" in normalized_content
    assert "terminal task success, task failure, or reward alone" in normalized_content
    assert "Do not choose the lesser of two flawed actions" in normalized_content
    assert "Repaired, edited, or otherwise synthetic actions" in normalized_content
