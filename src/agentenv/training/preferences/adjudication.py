from collections.abc import Sequence

from agentenv.training.preferences.hashing import (
    hash_preference_comparison_candidate_record,
)
from agentenv.training.preferences.schema import (
    PreferenceAdjudicationRecord,
    PreferenceAdjudicationSource,
    PreferenceComparisonCandidateRecord,
    PreferenceRubricProvenance,
)


def build_pending_preference_adjudication_records(
    comparison_candidates: Sequence[PreferenceComparisonCandidateRecord],
    *,
    rubric_provenance: PreferenceRubricProvenance,
) -> tuple[PreferenceAdjudicationRecord, ...]:
    _index_candidates(comparison_candidates)
    return tuple(
        PreferenceAdjudicationRecord(
            source=_build_adjudication_source(candidate),
            rubric_provenance=rubric_provenance,
            review_status="not_reviewed",
        )
        for candidate in comparison_candidates
    )


def validate_preference_adjudication_records(
    records: Sequence[PreferenceAdjudicationRecord],
    comparison_candidates: Sequence[PreferenceComparisonCandidateRecord],
    *,
    rubric_provenance: PreferenceRubricProvenance,
) -> None:
    candidates_by_id = _index_candidates(comparison_candidates)
    records_by_id = _index_adjudications(records)

    missing = sorted(set(candidates_by_id) - set(records_by_id))
    if missing:
        raise ValueError(
            "Preference adjudication records are missing comparison candidates: "
            + ", ".join(missing)
        )
    unknown = sorted(set(records_by_id) - set(candidates_by_id))
    if unknown:
        raise ValueError(
            "Preference adjudication records contain unknown comparison candidates: "
            + ", ".join(unknown)
        )

    for candidate_id, candidate in candidates_by_id.items():
        record = records_by_id[candidate_id]
        if record.source != _build_adjudication_source(candidate):
            raise ValueError(
                "Preference adjudication source provenance mismatch for candidate "
                f"{candidate_id}"
            )
        if record.rubric_provenance != rubric_provenance:
            raise ValueError(
                "Preference adjudication rubric provenance mismatch for candidate "
                f"{candidate_id}"
            )


def _build_adjudication_source(
    candidate: PreferenceComparisonCandidateRecord,
) -> PreferenceAdjudicationSource:
    return PreferenceAdjudicationSource(
        comparison_candidate_id=candidate.comparison_candidate_id,
        source_preference_comparison_candidate_record_hash=(
            hash_preference_comparison_candidate_record(candidate)
        ),
        alternative_a_id=candidate.alternative_a.alternative_id,
        alternative_b_id=candidate.alternative_b.alternative_id,
    )


def _index_candidates(
    candidates: Sequence[PreferenceComparisonCandidateRecord],
) -> dict[str, PreferenceComparisonCandidateRecord]:
    by_id: dict[str, PreferenceComparisonCandidateRecord] = {}
    for candidate in candidates:
        candidate_id = candidate.comparison_candidate_id
        if candidate_id in by_id:
            raise ValueError(
                f"Duplicate preference comparison candidate id: {candidate_id}"
            )
        by_id[candidate_id] = candidate
    return by_id


def _index_adjudications(
    records: Sequence[PreferenceAdjudicationRecord],
) -> dict[str, PreferenceAdjudicationRecord]:
    by_id: dict[str, PreferenceAdjudicationRecord] = {}
    for record in records:
        candidate_id = record.source.comparison_candidate_id
        if candidate_id in by_id:
            raise ValueError(
                "Duplicate preference adjudication for comparison candidate: "
                f"{candidate_id}"
            )
        by_id[candidate_id] = record
    return by_id
