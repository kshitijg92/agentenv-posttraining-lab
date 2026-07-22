from datetime import datetime, timedelta
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.models.schema import MessageId
from agentenv.training.preferences.hashing import (
    PREFERENCE_ACTION_PROJECTION_VERSION,
    PREFERENCE_MESSAGE_PROJECTION_VERSION,
    build_preference_alternative_id,
    build_preference_comparison_candidate_id,
    build_preference_pair_id,
    build_preference_rollout_evidence_id,
    build_preference_shared_context_id,
    hash_preference_action,
)
from agentenv.trajectories.schema import ArtifactRef, ReviewDecision, ReviewStatus


PreferenceComparisonCandidateRecordSchemaVersion = Literal[
    "preference_comparison_candidate_record_v0"
]
PreferenceDiscoveryMethod = Literal["exact_shared_context_distinct_assistant_actions"]
PreferenceTrainingSplit = Literal["practice", "dev"]
PreferenceMessageProjectionVersion = Literal["preference_message_projection_v0"]
PreferenceActionProjectionVersion = Literal["preference_action_projection_v0"]
PreferenceAdjudicationRecordSchemaVersion = Literal["preference_adjudication_record_v0"]
PreferencePairRecordSchemaVersion = Literal["preference_pair_record_v0"]
PreferenceAdjudicationDecision = Literal[
    "preferred",
    "tie",
    "ambiguous",
    "invalid",
]
PreferenceAdjudicationScope = Literal["overall_action_preference"]

PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION: PreferenceComparisonCandidateRecordSchemaVersion = "preference_comparison_candidate_record_v0"
PREFERENCE_ADJUDICATION_RECORD_SCHEMA_VERSION: PreferenceAdjudicationRecordSchemaVersion = "preference_adjudication_record_v0"
PREFERENCE_PAIR_RECORD_SCHEMA_VERSION: PreferencePairRecordSchemaVersion = (
    "preference_pair_record_v0"
)

ContentHash = Annotated[
    str,
    Field(pattern=r"^xxh64:[0-9a-f]{16}$", strict=True),
]


class PreferenceDiscoveryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discovery_method: PreferenceDiscoveryMethod
    discovery_version: str = Field(min_length=1)
    discovery_code_hash: ContentHash


class PreferenceTaskProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    split: PreferenceTrainingSplit
    task_manifest_hash: ContentHash
    task_record_hash: ContentHash
    required_task_files_hash: ContentHash
    full_task_dir_hash: ContentHash
    seed_workspace_hash: ContentHash


class PreferenceSharedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared_context_id: str = Field(min_length=1)
    message_projection_version: PreferenceMessageProjectionVersion
    task_provenance: PreferenceTaskProvenance
    harness_runtime_hash: ContentHash
    ordered_message_hashes: list[ContentHash] = Field(min_length=2)
    canonical_workspace_hash_before_action: ContentHash

    @model_validator(mode="after")
    def validate_shared_context_id(self) -> "PreferenceSharedContext":
        if self.message_projection_version != PREFERENCE_MESSAGE_PROJECTION_VERSION:
            raise ValueError("unsupported preference message projection version")
        expected_id = build_preference_shared_context_id(
            task_provenance=self.task_provenance.model_dump(mode="json"),
            harness_runtime_hash=self.harness_runtime_hash,
            ordered_message_hashes=self.ordered_message_hashes,
            canonical_workspace_hash_before_action=(
                self.canonical_workspace_hash_before_action
            ),
        )
        if self.shared_context_id != expected_id:
            raise ValueError(
                "shared_context_id must be derived from the exact shared state"
            )
        return self


class PreferenceRolloutEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["original_rollout"]
    continuation_provenance: Literal["executed_source_trajectory"]
    evidence_id: str = Field(min_length=1)
    source_training_candidate_record_hash: ContentHash
    source_trajectory_record_hash: ContentHash
    trajectory_id: str = Field(min_length=1)
    eval_suite_id: str | None = Field(default=None, min_length=1)
    eval_run_id: str = Field(min_length=1)
    eval_attempt_id: str = Field(min_length=1)
    agent_attempt_id: str = Field(min_length=1)
    source_policy_id: str = Field(min_length=1)
    source_trajectory_review_status: ReviewStatus
    source_trajectory_review_decision: ReviewDecision | None = None
    source_prompt_loop_result_ref: ArtifactRef
    prompt_builder_version: str = Field(min_length=1)
    prompt_builder_code_hash: ContentHash
    assistant_message_id: MessageId
    assistant_message_index: int = Field(ge=2, strict=True)
    continuation_message_count: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_rollout_evidence(self) -> "PreferenceRolloutEvidence":
        if self.source_prompt_loop_result_ref.content_hash is None:
            raise ValueError("preference rollout evidence must be hash-pinned")
        if self.source_trajectory_review_status == "not_reviewed":
            if self.source_trajectory_review_decision is not None:
                raise ValueError(
                    "not_reviewed source trajectories cannot include a decision"
                )
        elif self.source_trajectory_review_decision is None:
            raise ValueError("reviewed source trajectories require a decision")
        expected_evidence_id = build_preference_rollout_evidence_id(
            source_training_candidate_record_hash=(
                self.source_training_candidate_record_hash
            ),
            source_trajectory_record_hash=self.source_trajectory_record_hash,
            assistant_message_id=self.assistant_message_id,
        )
        if self.evidence_id != expected_evidence_id:
            raise ValueError(
                "evidence_id must be derived from its candidate, trajectory, and "
                "assistant occurrence"
            )
        return self


class PreferenceActionAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alternative_id: str = Field(min_length=1)
    action_projection_version: PreferenceActionProjectionVersion
    action_hash: ContentHash
    assistant_content: str
    rollout_evidence: list[PreferenceRolloutEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_action_and_evidence(self) -> "PreferenceActionAlternative":
        if self.action_projection_version != PREFERENCE_ACTION_PROJECTION_VERSION:
            raise ValueError("unsupported preference action projection version")
        if self.action_hash != hash_preference_action(self.assistant_content):
            raise ValueError("action_hash must match exact assistant content")
        evidence_ids = [record.evidence_id for record in self.rollout_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("preference alternative evidence ids must be unique")
        return self


class PreferenceComparisonCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: PreferenceComparisonCandidateRecordSchemaVersion = (
        PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION
    )
    comparison_candidate_id: str = Field(min_length=1)
    discovery_provenance: PreferenceDiscoveryProvenance
    shared_context: PreferenceSharedContext
    alternative_a: PreferenceActionAlternative
    alternative_b: PreferenceActionAlternative

    @model_validator(mode="after")
    def validate_unlabeled_comparison(self) -> "PreferenceComparisonCandidateRecord":
        context_id = self.shared_context.shared_context_id
        for alternative in (self.alternative_a, self.alternative_b):
            expected_id = build_preference_alternative_id(
                shared_context_id=context_id,
                action_hash=alternative.action_hash,
            )
            if alternative.alternative_id != expected_id:
                raise ValueError(
                    "alternative_id must be derived from context and action hash"
                )

        if self.alternative_a.action_hash >= self.alternative_b.action_hash:
            raise ValueError(
                "unlabeled alternatives must use canonical action-hash ordering"
            )
        evidence_a = {
            record.evidence_id for record in self.alternative_a.rollout_evidence
        }
        evidence_b = {
            record.evidence_id for record in self.alternative_b.rollout_evidence
        }
        if evidence_a & evidence_b:
            raise ValueError("comparison alternatives cannot share rollout evidence")

        expected_candidate_id = build_preference_comparison_candidate_id(
            shared_context_id=context_id,
            alternative_a_id=self.alternative_a.alternative_id,
            alternative_b_id=self.alternative_b.alternative_id,
        )
        if self.comparison_candidate_id != expected_candidate_id:
            raise ValueError(
                "comparison_candidate_id must be derived from its unordered pair"
            )
        return self


class PreferenceAdjudicationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_candidate_id: str = Field(min_length=1)
    source_preference_comparison_candidate_record_hash: ContentHash
    alternative_a_id: str = Field(min_length=1)
    alternative_b_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_distinct_alternatives(self) -> "PreferenceAdjudicationSource":
        if self.alternative_a_id == self.alternative_b_id:
            raise ValueError("preference adjudication alternatives must be distinct")
        return self


class PreferenceRubricProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adjudication_scope: PreferenceAdjudicationScope
    rubric_id: str = Field(min_length=1)
    rubric_version: str = Field(min_length=1)
    rubric_ref: ArtifactRef

    @model_validator(mode="after")
    def validate_hash_pinned_rubric(self) -> "PreferenceRubricProvenance":
        if self.rubric_ref.content_hash is None:
            raise ValueError("preference adjudication rubric must be hash-pinned")
        return self


class HumanPreferenceReviewerProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_type: Literal["human"]
    reviewer_id: str = Field(min_length=1)


class DeterministicPreferenceReviewerProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_type: Literal["deterministic_auditor"]
    auditor_id: str = Field(min_length=1)
    auditor_version: str = Field(min_length=1)
    auditor_code_hash: ContentHash
    auditor_configuration_hash: ContentHash


class LLMJudgePreferenceReviewerProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_type: Literal["llm_judge"]
    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    judge_prompt_ref: ArtifactRef
    model_input_protocol_ref: ArtifactRef
    decoding_config_ref: ArtifactRef

    @model_validator(mode="after")
    def validate_hash_pinned_judge_inputs(
        self,
    ) -> "LLMJudgePreferenceReviewerProvenance":
        refs = {
            "judge_prompt_ref": self.judge_prompt_ref,
            "model_input_protocol_ref": self.model_input_protocol_ref,
            "decoding_config_ref": self.decoding_config_ref,
        }
        for field_name, artifact_ref in refs.items():
            if artifact_ref.content_hash is None:
                raise ValueError(f"{field_name} must be hash-pinned")
        return self


PreferenceReviewerProvenance: TypeAlias = Annotated[
    HumanPreferenceReviewerProvenance
    | DeterministicPreferenceReviewerProvenance
    | LLMJudgePreferenceReviewerProvenance,
    Field(discriminator="reviewer_type"),
]


class PreferenceAdjudicationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: PreferenceAdjudicationRecordSchemaVersion = (
        PREFERENCE_ADJUDICATION_RECORD_SCHEMA_VERSION
    )
    source: PreferenceAdjudicationSource
    rubric_provenance: PreferenceRubricProvenance
    review_status: ReviewStatus
    review_id: str | None = Field(default=None, min_length=1)
    reviewer_provenance: PreferenceReviewerProvenance | None = None
    review_decision: PreferenceAdjudicationDecision | None = None
    preferred_alternative_id: str | None = Field(default=None, min_length=1)
    decision_reason: str | None = Field(default=None, min_length=1)
    reviewed_at_utc: datetime | None = None

    @model_validator(mode="after")
    def validate_adjudication_state(self) -> "PreferenceAdjudicationRecord":
        review_details = (
            self.review_id,
            self.reviewer_provenance,
            self.review_decision,
            self.preferred_alternative_id,
            self.decision_reason,
            self.reviewed_at_utc,
        )
        if self.review_status == "not_reviewed":
            if any(value is not None for value in review_details):
                raise ValueError(
                    "not_reviewed preference adjudications cannot include review "
                    "details"
                )
            return self

        if self.review_id is None:
            raise ValueError("reviewed preference adjudications require review_id")
        if self.reviewer_provenance is None:
            raise ValueError(
                "reviewed preference adjudications require reviewer provenance"
            )
        if self.review_decision is None:
            raise ValueError(
                "reviewed preference adjudications require review_decision"
            )
        if self.decision_reason is None or not self.decision_reason.strip():
            raise ValueError(
                "reviewed preference adjudications require a nonempty decision_reason"
            )
        if self.reviewed_at_utc is None:
            raise ValueError(
                "reviewed preference adjudications require reviewed_at_utc"
            )
        if (
            self.reviewed_at_utc.utcoffset() is None
            or self.reviewed_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("reviewed_at_utc must be timezone-aware UTC")

        alternative_ids = {
            self.source.alternative_a_id,
            self.source.alternative_b_id,
        }
        if self.review_decision == "preferred":
            if self.preferred_alternative_id not in alternative_ids:
                raise ValueError(
                    "preferred adjudications must select exactly one source alternative"
                )
        elif self.preferred_alternative_id is not None:
            raise ValueError(
                "tie, ambiguous, and invalid adjudications cannot select a "
                "preferred alternative"
            )
        return self


class PreferencePairSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_candidate_id: str = Field(min_length=1)
    source_preference_comparison_candidate_record_hash: ContentHash
    source_preference_adjudication_record_hash: ContentHash


class PreferencePairRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: PreferencePairRecordSchemaVersion = (
        PREFERENCE_PAIR_RECORD_SCHEMA_VERSION
    )
    preference_pair_id: str = Field(min_length=1)
    source: PreferencePairSource

    @model_validator(mode="after")
    def validate_preference_pair_id(self) -> "PreferencePairRecord":
        expected_id = build_preference_pair_id(
            comparison_candidate_id=self.source.comparison_candidate_id,
            source_preference_comparison_candidate_record_hash=(
                self.source.source_preference_comparison_candidate_record_hash
            ),
            source_preference_adjudication_record_hash=(
                self.source.source_preference_adjudication_record_hash
            ),
        )
        if self.preference_pair_id != expected_id:
            raise ValueError(
                "preference_pair_id must be derived from its exact source records"
            )
        return self
