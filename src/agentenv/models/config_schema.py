import re
from pathlib import PurePosixPath
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


TokenUsageCapability = Literal["native", "unavailable"]
AgentActionFormat = Literal["prompt_only", "json_schema"]
_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONTENT_HASH_RE = re.compile(r"^xxh64:[0-9a-f]{16}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_usage: TokenUsageCapability
    supports_seed: bool
    supports_stop: bool
    supports_top_k: bool


class PromptAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_suffix: str | None = Field(default=None, min_length=1)


class PinnedModelInputProtocolRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if "\\" in value or (
            len(value) >= 2 and value[0].isalpha() and value[1] == ":"
        ):
            raise ValueError("model input protocol path must be POSIX-style")
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or path.parts == (".",):
            raise ValueError("model input protocol path must be relative")
        if str(path) != value:
            raise ValueError("model input protocol path must be canonical")
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        if not _CONTENT_HASH_RE.fullmatch(value):
            raise ValueError("content_hash must use the xxh64:<16 lowercase hex> form")
        return value


class BaseModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["model_config_v0"]
    model_id: str = Field(min_length=1)
    base_url_env: str | None = Field(default=None, min_length=1)
    capabilities: ModelCapabilities

    @field_validator("base_url_env")
    @classmethod
    def validate_base_url_env_name(cls, value: str | None) -> str | None:
        return _validate_env_var_name(value)


class OpenAICompatibleChatModelConfig(BaseModelConfig):
    provider: Literal["openai_compatible_chat"]
    api_key_env: str | None = Field(default=None, min_length=1)
    prompt_adapter: PromptAdapterConfig | None = None
    agent_action_format: AgentActionFormat = "prompt_only"

    @field_validator("api_key_env")
    @classmethod
    def validate_api_key_env_name(cls, value: str | None) -> str | None:
        return _validate_env_var_name(value)


class OllamaGenerateModelConfig(BaseModelConfig):
    provider: Literal["ollama_generate"]
    model_manifest_digest: str = Field(min_length=1)
    model_input_protocol: PinnedModelInputProtocolRef
    agent_action_format: AgentActionFormat = "prompt_only"

    @field_validator("model_manifest_digest")
    @classmethod
    def validate_model_manifest_digest(cls, value: str) -> str:
        if not _SHA256_DIGEST_RE.fullmatch(value):
            raise ValueError(
                "model_manifest_digest must use the sha256:<64 lowercase hex> form"
            )
        return value


ModelConfig: TypeAlias = Annotated[
    OpenAICompatibleChatModelConfig | OllamaGenerateModelConfig,
    Field(discriminator="provider"),
]


def _validate_env_var_name(value: str | None) -> str | None:
    if value is None:
        return value
    if not _ENV_VAR_RE.fullmatch(value):
        raise ValueError("environment variable names must be shell-safe")
    return value
