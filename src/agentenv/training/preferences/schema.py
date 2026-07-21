from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.models.schema import MessageId
from agentenv.training.preferences.hashing import (
    PREFERENCE_ACTION_PROJECTION_VERSION,
    PREFERENCE_MESSAGE_PROJECTION_VERSION,
    build_preference_alternative_id,
    build_preference_comparison_candidate_id,
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

PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION: PreferenceComparisonCandidateRecordSchemaVersion = "preference_comparison_candidate_record_v0"

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
