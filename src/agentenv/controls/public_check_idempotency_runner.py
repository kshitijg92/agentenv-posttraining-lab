import tempfile
from pathlib import Path
from subprocess import TimeoutExpired

from agentenv.controls.public_check_idempotency_schema import (
    PUBLIC_CHECK_IDEMPOTENCY_CALIBRATION_SCHEMA_VERSION,
    CompletedPublicCheckRun,
    FailedPublicCheckRun,
    HashPinnedArtifactRef,
    PublicCheckIdempotencyCalibration,
    PublicCheckOutputNormalizationContext,
    SinglePublicCheckRun,
    derive_non_idempotency_reasons,
    derive_public_check_idempotency_status,
)
from agentenv.controls.public_check_output_normalizer import (
    PUBLIC_CHECK_OUTPUT_NORMALIZER_VERSION,
    compute_public_check_output_normalizer_code_hash,
    hash_normalized_public_check_result,
)
from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.hashing import hash_directory, hash_file
from agentenv.runners.public_check_runner import run_public_check
from agentenv.security.secrets import redact_secrets
from agentenv.tasks.schema import PublicCheck
from agentenv.tasks.validate import load_task_manifest


DEFAULT_PUBLIC_CHECK_IDEMPOTENCY_REPEATS = 2


def run_declared_public_check_idempotency_calibrations(
    *,
    task_manifest_path: Path,
    artifact_root: Path,
    output_dir: Path,
    repeat_count: int = DEFAULT_PUBLIC_CHECK_IDEMPOTENCY_REPEATS,
) -> list[PublicCheckIdempotencyCalibration]:
    if repeat_count < 2:
        raise ValueError("public-check idempotency repeat_count must be at least 2")

    task_manifest_path = task_manifest_path.resolve()
    artifact_root = artifact_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir == artifact_root or not output_dir.is_relative_to(artifact_root):
        raise ValueError("public-check output_dir must be inside artifact_root")

    manifest = load_task_manifest(task_manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    task_manifest_hash = hash_file(task_manifest_path)
    calibrations: list[PublicCheckIdempotencyCalibration] = []
    for public_check_index, public_check in _declared_idempotent_checks(
        manifest.public_checks
    ):
        calibrations.append(
            _run_public_check_calibration(
                task_id=manifest.id,
                task_manifest_path=task_manifest_path,
                task_manifest_hash=task_manifest_hash,
                public_check=public_check,
                public_check_index=public_check_index,
                artifact_root=artifact_root,
                output_dir=output_dir,
                repeat_count=repeat_count,
                timeout_seconds=manifest.limits.timeout_seconds,
            )
        )
    return calibrations


def _declared_idempotent_checks(
    public_checks: list[PublicCheck],
) -> list[tuple[int, PublicCheck]]:
    return [
        (index, public_check)
        for index, public_check in enumerate(public_checks)
        if public_check.are_tests_idempotent
    ]


def _run_public_check_calibration(
    *,
    task_id: str,
    task_manifest_path: Path,
    task_manifest_hash: str,
    public_check: PublicCheck,
    public_check_index: int,
    artifact_root: Path,
    output_dir: Path,
    repeat_count: int,
    timeout_seconds: int,
) -> PublicCheckIdempotencyCalibration:
    check_output_dir = output_dir / (
        f"{task_id}__public_check_{public_check_index + 1:03d}"
    )
    check_output_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix="agentenv-public-check-idempotency-") as raw:
        scratch_root = Path(raw).resolve()
        workspace = prepare_agent_workspace(
            load_task_manifest(task_manifest_path),
            task_manifest_path,
            workspace_parent=scratch_root / "seed_workspace_copy",
        )
        runner_temp_root = scratch_root / "runner_temp"
        context = PublicCheckOutputNormalizationContext(
            workspace_root=workspace.path.as_posix(),
            runner_temp_root=runner_temp_root.as_posix(),
        )
        runs = [
            _run_public_check_once(
                command=public_check.command,
                run_index=run_index,
                workspace_path=workspace.path,
                runner_temp_root=runner_temp_root,
                context=context,
                artifact_root=artifact_root,
                check_output_dir=check_output_dir,
                timeout_seconds=timeout_seconds,
            )
            for run_index in range(repeat_count)
        ]

    return PublicCheckIdempotencyCalibration(
        schema_version=PUBLIC_CHECK_IDEMPOTENCY_CALIBRATION_SCHEMA_VERSION,
        task_id=task_id,
        task_manifest_hash=task_manifest_hash,
        public_check_index=public_check_index,
        command=public_check.command,
        normalizer_version=PUBLIC_CHECK_OUTPUT_NORMALIZER_VERSION,
        normalizer_code_hash=compute_public_check_output_normalizer_code_hash(),
        normalization_context=context,
        repeat_count=repeat_count,
        status=derive_public_check_idempotency_status(runs),
        non_idempotency_reasons=derive_non_idempotency_reasons(runs),
        runs=runs,
    )


def _run_public_check_once(
    *,
    command: str,
    run_index: int,
    workspace_path: Path,
    runner_temp_root: Path,
    context: PublicCheckOutputNormalizationContext,
    artifact_root: Path,
    check_output_dir: Path,
    timeout_seconds: int,
) -> SinglePublicCheckRun:
    workspace_hash_before = hash_directory(workspace_path)
    try:
        result = run_public_check(
            command,
            workspace=workspace_path,
            timeout_seconds=timeout_seconds,
            runner_temp_root=runner_temp_root,
        )
    except TimeoutExpired as exc:
        workspace_hash_after = hash_directory(workspace_path)
        stdout = _optional_stream_text(exc.stdout)
        stderr = _optional_stream_text(exc.stderr)
        return FailedPublicCheckRun(
            run_index=run_index,
            status="FAILURE",
            failure_mode="TIMEOUT",
            canonical_workspace_hash_before=workspace_hash_before,
            canonical_workspace_hash_after=workspace_hash_after,
            stdout=_write_optional_output_artifact(
                artifact_root=artifact_root,
                check_output_dir=check_output_dir,
                run_index=run_index,
                filename="stdout.txt",
                content=stdout,
            ),
            stderr=_write_optional_output_artifact(
                artifact_root=artifact_root,
                check_output_dir=check_output_dir,
                run_index=run_index,
                filename="stderr.txt",
                content=stderr,
            ),
            error_class=type(exc).__name__,
            error_message=f"Public check timed out after {timeout_seconds} seconds.",
        )
    except Exception as exc:
        workspace_hash_after = hash_directory(workspace_path)
        return FailedPublicCheckRun(
            run_index=run_index,
            status="FAILURE",
            failure_mode="RUNNER_FAILURE",
            canonical_workspace_hash_before=workspace_hash_before,
            canonical_workspace_hash_after=workspace_hash_after,
            error_class=type(exc).__name__,
            error_message=_runner_failure_message(exc),
        )

    workspace_hash_after = hash_directory(workspace_path)
    stdout_ref = _write_output_artifact(
        artifact_root=artifact_root,
        check_output_dir=check_output_dir,
        run_index=run_index,
        filename="stdout.txt",
        content=result.stdout,
    )
    stderr_ref = _write_output_artifact(
        artifact_root=artifact_root,
        check_output_dir=check_output_dir,
        run_index=run_index,
        filename="stderr.txt",
        content=result.stderr,
    )
    return CompletedPublicCheckRun(
        run_index=run_index,
        status="COMPLETED",
        canonical_workspace_hash_before=workspace_hash_before,
        canonical_workspace_hash_after=workspace_hash_after,
        exit_code=result.returncode,
        stdout=stdout_ref,
        stderr=stderr_ref,
        normalized_result_hash=hash_normalized_public_check_result(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            context=context,
        ),
    )


def _write_optional_output_artifact(
    *,
    artifact_root: Path,
    check_output_dir: Path,
    run_index: int,
    filename: str,
    content: str | None,
) -> HashPinnedArtifactRef | None:
    if content is None:
        return None
    return _write_output_artifact(
        artifact_root=artifact_root,
        check_output_dir=check_output_dir,
        run_index=run_index,
        filename=filename,
        content=content,
    )


def _write_output_artifact(
    *,
    artifact_root: Path,
    check_output_dir: Path,
    run_index: int,
    filename: str,
    content: str,
) -> HashPinnedArtifactRef:
    run_dir = check_output_dir / f"run_{run_index + 1:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / filename
    path.write_text(content)
    return HashPinnedArtifactRef(
        path=path.relative_to(artifact_root).as_posix(),
        content_hash=hash_file(path),
    )


def _optional_stream_text(stream: object) -> str | None:
    if stream is None:
        return None
    if isinstance(stream, bytes):
        return redact_secrets(stream.decode(errors="replace"))
    return redact_secrets(str(stream))


def _runner_failure_message(exc: Exception) -> str:
    message = redact_secrets(str(exc))
    if message:
        return message
    return "Public check runner failed without an error message."
