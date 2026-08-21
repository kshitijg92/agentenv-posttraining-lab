from __future__ import annotations

from collections.abc import Callable
import gc
import os
import platform
from pathlib import Path
from typing import Any

import accelerate
import peft
import torch
import transformers

from agentenv.audits.runtime import (
    git_sha_or_unknown,
    git_worktree_state,
    harness_repo_root,
)
from agentenv.hashing import hash_directory, hash_json
from agentenv.training.lora.schema import (
    TrainingRuntimeConfig,
    TrainingRuntimeProvenance,
)
from agentenv.training.lora.state import get_model_logits


def capture_training_runtime_provenance(
    runtime: TrainingRuntimeConfig,
    *,
    objective_code_dir: Path,
) -> TrainingRuntimeProvenance:
    repo_root = harness_repo_root()
    requested_device = runtime.device
    cuda_available = torch.cuda.is_available()
    if requested_device == "cuda" and cuda_available:
        device_index = torch.cuda.current_device()
        device_properties = torch.cuda.get_device_properties(device_index)
        observed_device = f"cuda:{device_index}"
        accelerator_name = device_properties.name
        accelerator_total_memory_bytes = device_properties.total_memory
    elif requested_device == "cuda":
        observed_device = "cuda:unavailable"
        accelerator_name = None
        accelerator_total_memory_bytes = None
    else:
        observed_device = "cpu"
        accelerator_name = platform.processor() or platform.machine() or "unknown"
        accelerator_total_memory_bytes = None

    git_worktree_dirty, git_diff_hash = git_worktree_state(repo_root)
    return TrainingRuntimeProvenance(
        python_version=platform.python_version(),
        platform=platform.platform(),
        torch_version=torch.__version__,
        transformers_version=transformers.__version__,
        peft_version=peft.__version__,
        accelerate_version=accelerate.__version__,
        requested_device=requested_device,
        observed_device=observed_device,
        accelerator_name=accelerator_name,
        accelerator_total_memory_bytes=accelerator_total_memory_bytes,
        torch_cuda_version=torch.version.cuda,
        cublas_workspace_config=runtime.cublas_workspace_config,
        git_sha_or_unknown=git_sha_or_unknown(repo_root),
        git_worktree_dirty=git_worktree_dirty,
        git_diff_hash=git_diff_hash,
        trainer_code_hash=hash_json(
            {
                "shared_lora": hash_directory(Path(__file__).resolve().parent),
                "objective": hash_directory(objective_code_dir.resolve()),
            }
        ),
    )


def configure_process_determinism(runtime: TrainingRuntimeConfig) -> None:
    expected = runtime.cublas_workspace_config
    observed = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    if observed is not None and observed != expected:
        raise ValueError(
            "CUBLAS_WORKSPACE_CONFIG conflicts with the pinned training config; "
            f"observed={observed!r}, expected={expected!r}"
        )
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = expected


def require_requested_training_device(
    provenance: TrainingRuntimeProvenance,
) -> None:
    if (
        provenance.requested_device == "cuda"
        and provenance.observed_device == "cuda:unavailable"
    ):
        raise ValueError("training config requires CUDA, but CUDA is unavailable")


def resolve_training_device(runtime: TrainingRuntimeConfig) -> torch.device:
    if runtime.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("training config requires CUDA, but CUDA is unavailable")
    return torch.device(runtime.device)


def set_training_determinism(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)


def configure_model_for_training(
    model: Any,
    runtime: TrainingRuntimeConfig,
) -> None:
    model.config.use_cache = False
    if runtime.gradient_checkpointing:
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
        model.enable_input_require_grads()


def configure_model_for_inference(model: Any) -> None:
    model.config.use_cache = False
    model.eval()


def build_probe_input_ids(
    input_ids: list[int],
    *,
    token_count: int,
    device: torch.device,
) -> torch.Tensor:
    selected_count = min(token_count, len(input_ids))
    return torch.tensor(
        [input_ids[:selected_count]],
        dtype=torch.long,
        device=device,
    )


def get_last_token_logits(model: Any, input_ids: torch.Tensor) -> torch.Tensor:
    model.eval()
    with torch.inference_mode():
        outputs = model(
            input_ids=input_ids,
            attention_mask=torch.ones_like(input_ids),
            use_cache=False,
        )
    return get_model_logits(outputs)[:, -1, :].detach().cpu().clone()


def release_accelerator_memory(device: torch.device) -> None:
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()


def notify_stage(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is not None:
        callback(stage)
