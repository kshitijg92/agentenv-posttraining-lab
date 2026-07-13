from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class OllamaProviderRuntimeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama"]
    model_id: str = Field(min_length=1)
    model_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    server_version: str = Field(min_length=1)


ProviderRuntimeProvenance: TypeAlias = OllamaProviderRuntimeProvenance
