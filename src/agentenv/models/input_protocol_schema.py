import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentenv.artifacts.base import validate_relative_artifact_ref


MODEL_INPUT_PROTOCOL_SCHEMA_VERSION = "model_input_protocol_v0"
ModelInputSerializationMode = Literal["generation", "completed_transcript"]
ModelInputMessageField = Literal["role", "content"]

_HF_REPOSITORY_ID_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_HF_COMMIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class HuggingFaceRevisionPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)

    @field_validator("repository_id")
    @classmethod
    def validate_repository_id(cls, value: str) -> str:
        if not _HF_REPOSITORY_ID_RE.fullmatch(value):
            raise ValueError("repository_id must be an owner/repository identifier")
        return value

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if not _HF_COMMIT_REVISION_RE.fullmatch(value):
            raise ValueError("revision must be an immutable 40-character commit id")
        return value


class UpstreamTokenizerFilePin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_path: str = Field(min_length=1)
    sha256: str = Field(min_length=1)

    @field_validator("repository_path")
    @classmethod
    def validate_repository_path(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must use the sha256:<64 lowercase hex> form")
        return value


class SpecialTokenPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    token_id: int = Field(ge=0)


class RequiredSpecialTokenPins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_start: SpecialTokenPin
    end_of_turn: SpecialTokenPin
    padding: SpecialTokenPin


class TokenizerPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: HuggingFaceRevisionPin
    upstream_files: tuple[UpstreamTokenizerFilePin, ...] = Field(min_length=1)
    required_special_tokens: RequiredSpecialTokenPins

    @model_validator(mode="after")
    def validate_unique_upstream_file_paths(self) -> "TokenizerPin":
        paths = [upstream_file.repository_path for upstream_file in self.upstream_files]
        if len(set(paths)) != len(paths):
            raise ValueError("upstream tokenizer repository paths must be unique")
        return self


class ChatTemplatePin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_repository_path: str = Field(min_length=1)
    source_field: Literal["chat_template"]
    local_snapshot_ref: str = Field(min_length=1)
    sha256: str = Field(min_length=1)

    @field_validator("source_repository_path", "local_snapshot_ref")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must use the sha256:<64 lowercase hex> form")
        return value


class ModelInputProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["model_input_protocol_v0"]
    protocol_id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    model_checkpoint: HuggingFaceRevisionPin
    tokenizer: TokenizerPin
    chat_template: ChatTemplatePin
    supported_serialization_modes: tuple[ModelInputSerializationMode, ...] = Field(
        min_length=1
    )
    message_fields: tuple[ModelInputMessageField, ...] = Field(min_length=1)
    tool_serialization: Literal["agentenv_json_content"]
    native_tool_serialization: Literal["unsupported"]

    @model_validator(mode="after")
    def validate_protocol_contract(self) -> "ModelInputProtocol":
        modes = self.supported_serialization_modes
        if len(set(modes)) != len(modes):
            raise ValueError("supported_serialization_modes cannot contain duplicates")
        if set(modes) != {"generation", "completed_transcript"}:
            raise ValueError(
                "model_input_protocol_v0 requires generation and "
                "completed_transcript serialization"
            )
        if self.message_fields != ("role", "content"):
            raise ValueError("model_input_protocol_v0 renders exactly role and content")
        tokenizer_paths = {
            upstream_file.repository_path
            for upstream_file in self.tokenizer.upstream_files
        }
        if self.chat_template.source_repository_path not in tokenizer_paths:
            raise ValueError(
                "chat-template source_repository_path must name a pinned "
                "upstream tokenizer file"
            )
        return self
