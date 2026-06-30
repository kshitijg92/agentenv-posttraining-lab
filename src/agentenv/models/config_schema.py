import re
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


TokenUsageCapability = Literal["native", "unavailable"]
_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_usage: TokenUsageCapability
    supports_seed: bool
    supports_stop: bool
    supports_top_k: bool


class PromptAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_suffix: str | None = Field(default=None, min_length=1)


class OpenAICompatibleChatModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["model_config_v0"]
    provider: Literal["openai_compatible_chat"]
    model_id: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, min_length=1)
    base_url_env: str | None = Field(default=None, min_length=1)
    capabilities: ModelCapabilities
    prompt_adapter: PromptAdapterConfig | None = None

    @field_validator("api_key_env", "base_url_env")
    @classmethod
    def validate_env_var_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _ENV_VAR_RE.fullmatch(value):
            raise ValueError("environment variable names must be shell-safe")
        return value


ModelConfig: TypeAlias = OpenAICompatibleChatModelConfig
