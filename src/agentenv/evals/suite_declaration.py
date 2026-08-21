from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.artifacts.base import (
    load_json_object,
    validate_relative_artifact_ref,
)
from agentenv.artifacts.payloads import (
    DecodingConfigProvenance,
    EvalTaskHashes,
    ModelConfigProvenance,
)
from agentenv.audits.schema import HarnessRuntimeProvenance
from agentenv.hashing import hash_json


EvalSuiteDeclarationSchemaVersion = Literal["eval_suite_declaration_v0"]

EVAL_SUITE_DECLARATION_SCHEMA_VERSION: EvalSuiteDeclarationSchemaVersion = (
    "eval_suite_declaration_v0"
)
EVAL_SUITE_DECLARATION_FILENAME = "eval_suite_declaration.json"


class PlannedEvalAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    attempt_index: int = Field(ge=0, strict=True)
    artifact_dir: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_artifact_dir(self) -> "PlannedEvalAttempt":
        validate_relative_artifact_ref(self.artifact_dir)
        return self


class PlannedEvalPolicyRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: str = Field(min_length=1)
    eval_run_id: str = Field(min_length=1)
    artifact_dir: str = Field(min_length=1)
    model_config_provenance: ModelConfigProvenance | None = None
    decoding_config_provenance: DecodingConfigProvenance | None = None
    planned_attempts: list[PlannedEvalAttempt] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy_run(self) -> "PlannedEvalPolicyRun":
        validate_relative_artifact_ref(self.artifact_dir)
        if (self.model_config_provenance is None) != (
            self.decoding_config_provenance is None
        ):
            raise ValueError(
                "model and decoding config provenance must both be set or both null"
            )
        _require_unique(
            [attempt.eval_attempt_id for attempt in self.planned_attempts],
            field_name="eval_attempt_id",
        )
        _require_unique(
            [attempt.artifact_dir for attempt in self.planned_attempts],
            field_name="planned attempt artifact_dir",
        )
        return self


class EvalSuiteDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: EvalSuiteDeclarationSchemaVersion
    eval_suite_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    config_path: str = Field(min_length=1)
    config_hash: str = Field(min_length=1)
    task_hashes: EvalTaskHashes
    runtime_provenance: HarnessRuntimeProvenance
    policy_runs: list[PlannedEvalPolicyRun] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_declaration(self) -> "EvalSuiteDeclaration":
        _require_unique(
            [policy_run.policy for policy_run in self.policy_runs],
            field_name="policy",
        )
        _require_unique(
            [policy_run.eval_run_id for policy_run in self.policy_runs],
            field_name="eval_run_id",
        )
        _require_unique(
            [policy_run.artifact_dir for policy_run in self.policy_runs],
            field_name="policy artifact_dir",
        )
        _require_unique(
            [
                attempt.eval_attempt_id
                for policy_run in self.policy_runs
                for attempt in policy_run.planned_attempts
            ],
            field_name="eval_attempt_id",
        )
        _require_unique(
            [
                f"{policy_run.artifact_dir}/{attempt.artifact_dir}"
                for policy_run in self.policy_runs
                for attempt in policy_run.planned_attempts
            ],
            field_name="planned attempt artifact path",
        )
        return self


def load_eval_suite_declaration(path: Path) -> EvalSuiteDeclaration:
    return EvalSuiteDeclaration.model_validate(load_json_object(path))


def hash_eval_suite_declaration(declaration: EvalSuiteDeclaration) -> str:
    return hash_json(declaration.model_dump(mode="json"))


def _require_unique(values: list[str], *, field_name: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(
            f"Duplicate {field_name} value(s): " + ", ".join(duplicates)
        )
