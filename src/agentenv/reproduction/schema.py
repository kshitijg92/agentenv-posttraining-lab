from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from agentenv.artifacts.base import validate_relative_artifact_ref
from agentenv.reporting.policy_selection import (
    PolicySelectionBranch,
    PolicySelectionStatus,
)


ContentHash = str
TrainingArtifactKind = Literal["positive_sft_lora", "dpo_lora"]


class ArchivedTrainingArtifactSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    kind: TrainingArtifactKind
    artifact_dir: str = Field(min_length=1)
    expected_manifest_hash: ContentHash = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$"
    )

    @field_validator("artifact_dir")
    @classmethod
    def validate_artifact_dir(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)


class ExpectedPolicySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PolicySelectionStatus
    branch: PolicySelectionBranch
    selected_policy: str | None = None

    @model_validator(mode="after")
    def validate_selected_policy(self) -> "ExpectedPolicySelection":
        if self.status == "selected" and not self.selected_policy:
            raise ValueError("selected policy-selection status requires a policy id")
        if self.status == "abstained" and self.selected_policy is not None:
            raise ValueError("abstained policy-selection status cannot select a policy")
        return self


class ArchivedComparisonSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    eval_suite_dir: str = Field(min_length=1)
    expected_suite_manifest_hash: ContentHash = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$"
    )
    canonical_report: str = Field(min_length=1)
    expected_report_hash: ContentHash = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    expected_selection: ExpectedPolicySelection

    @field_validator("eval_suite_dir", "canonical_report")
    @classmethod
    def validate_repo_path(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)


class ArchivedReproductionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    task_pack: str = Field(min_length=1)
    training_artifacts: tuple[ArchivedTrainingArtifactSpec, ...] = Field(min_length=1)
    comparisons: tuple[ArchivedComparisonSpec, ...] = Field(min_length=1)

    @field_validator("task_pack")
    @classmethod
    def validate_task_pack(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @model_validator(mode="after")
    def validate_unique_declarations(self) -> "ArchivedReproductionPlan":
        _require_unique(
            (artifact.name for artifact in self.training_artifacts),
            "training artifact names",
        )
        _require_unique(
            (artifact.artifact_dir for artifact in self.training_artifacts),
            "training artifact directories",
        )
        _require_unique(
            (comparison.name for comparison in self.comparisons),
            "comparison names",
        )
        _require_unique(
            (comparison.eval_suite_dir for comparison in self.comparisons),
            "comparison suite directories",
        )
        _require_unique(
            (comparison.canonical_report for comparison in self.comparisons),
            "canonical report paths",
        )
        return self


def load_archived_reproduction_plan(path: Path) -> ArchivedReproductionPlan:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("Archived reproduction plan must contain a YAML object")
    return ArchivedReproductionPlan.model_validate(raw)


def _require_unique(values: Iterable[str], label: str) -> None:
    frozen = tuple(values)
    if len(frozen) != len(set(frozen)):
        raise ValueError(f"Archived reproduction plan requires unique {label}")
