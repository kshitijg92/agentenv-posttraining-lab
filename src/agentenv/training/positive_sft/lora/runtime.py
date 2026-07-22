from __future__ import annotations

import platform
from pathlib import Path
import os
import subprocess
import sys

import accelerate
import peft
import torch
import transformers

from agentenv.audits.runtime import git_sha_or_unknown, harness_repo_root
from agentenv.hashing import hash_bytes, hash_directory
from agentenv.training.positive_sft.lora.schema import (
    PositiveSFTLoRATrainingConfig,
    TrainingRuntimeProvenance,
)


def capture_training_runtime_provenance(
    config: PositiveSFTLoRATrainingConfig,
) -> TrainingRuntimeProvenance:
    repo_root = harness_repo_root()
    requested_device = config.runtime.device
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

    git_worktree_dirty, git_diff_hash = _git_worktree_state(repo_root)
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
        cublas_workspace_config=config.runtime.cublas_workspace_config,
        git_sha_or_unknown=git_sha_or_unknown(repo_root),
        git_worktree_dirty=git_worktree_dirty,
        git_diff_hash=git_diff_hash,
        trainer_code_hash=hash_directory(Path(__file__).resolve().parent),
    )


def configure_process_determinism(
    config: PositiveSFTLoRATrainingConfig,
) -> None:
    expected = config.runtime.cublas_workspace_config
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


def _git_worktree_state(repo_root: Path) -> tuple[bool, str]:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=10,
        )
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return True, hash_bytes(b"git-worktree-state-unavailable")
    if status.returncode != 0 or diff.returncode != 0:
        return True, hash_bytes(b"git-worktree-state-unavailable")
    payload = b"status\0" + status.stdout + b"\0diff\0" + diff.stdout
    return bool(status.stdout.strip()), hash_bytes(payload)


def python_executable() -> str:
    return sys.executable
