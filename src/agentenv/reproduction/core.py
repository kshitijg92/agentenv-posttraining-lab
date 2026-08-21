from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Iterator, Literal

from agentenv.artifacts import MANIFEST_FILENAME, prepare_artifact_output_dir
from agentenv.audits.runtime import (
    capture_harness_runtime_provenance,
    git_sha_or_unknown,
    git_worktree_state,
)
from agentenv.audits.schema import HarnessRuntimeProvenance
from agentenv.evals.schema import EvalConfig
from agentenv.evals.validate import load_eval_config
from agentenv.hashing import hash_file
from agentenv.orchestrators.eval_run import run_eval_config_all_policies
from agentenv.reporting.markdown import write_markdown_report
from agentenv.reproduction.deterministic_suite import (
    requires_operational_verification,
    verify_eval_suite_operational_expectations,
)
from agentenv.reproduction.schema import StoredEvidencePlan, load_stored_evidence_plan
from agentenv.reproduction.stored_evidence import (
    render_stored_evidence_verification,
    verify_stored_evidence,
)


CoreCheckStatus = Literal["PASS", "FAIL"]
CoreReproductionStatus = Literal["PASS", "FAIL"]

CORE_REPRODUCTION_REPORT_FILENAME = "reproduction_report.md"
STORED_EVIDENCE_SUMMARY_FILENAME = "stored_evidence_verification.md"
DEFAULT_STORED_EVIDENCE_PLAN = Path(
    "configs/reproduction/posttraining_result.yaml"
)
DEFAULT_DETERMINISTIC_EVAL_CONFIG = Path(
    "configs/eval/eval_quality_gate_repo_patch_python_v0.yaml"
)


@dataclass(frozen=True)
class CoreReproductionCheck:
    level: Literal[1, 2]
    check_id: str
    status: CoreCheckStatus
    detail: str


@dataclass(frozen=True)
class CanonicalArtifactIdentity:
    kind: str
    name: str
    path: str
    expected_hash: str


@dataclass(frozen=True)
class CoreReproductionResult:
    out_dir: Path
    command: str
    plan_name: str
    plan_hash: str
    git_sha: str
    git_worktree_dirty: bool
    git_diff_hash: str
    runtime_provenance: HarnessRuntimeProvenance
    checks: tuple[CoreReproductionCheck, ...]
    canonical_artifacts: tuple[CanonicalArtifactIdentity, ...]
    portability_blockers: tuple[str, ...]

    @property
    def status(self) -> CoreReproductionStatus:
        if self.checks and all(check.status == "PASS" for check in self.checks):
            return "PASS"
        return "FAIL"

    @property
    def report_path(self) -> Path:
        return self.out_dir / CORE_REPRODUCTION_REPORT_FILENAME

    def level_status(self, level: Literal[1, 2]) -> CoreReproductionStatus:
        checks = tuple(check for check in self.checks if check.level == level)
        if checks and all(check.status == "PASS" for check in checks):
            return "PASS"
        return "FAIL"


def run_core_reproduction(
    out_dir: Path,
    *,
    plan_path: Path = DEFAULT_STORED_EVIDENCE_PLAN,
    eval_config_path: Path = DEFAULT_DETERMINISTIC_EVAL_CONFIG,
    repo_root: Path = Path("."),
) -> CoreReproductionResult:
    """Run stored-evidence and deterministic-suite reproduction levels."""

    repo_root = repo_root.resolve()
    requested_out_dir = out_dir
    requested_plan_path = plan_path
    requested_eval_config_path = eval_config_path
    plan_path = _resolve_input_path(repo_root, plan_path)
    eval_config_path = _resolve_input_path(repo_root, eval_config_path)
    plan = load_stored_evidence_plan(plan_path)
    load_eval_config(eval_config_path)

    runtime_provenance = capture_harness_runtime_provenance(repo_root)
    git_sha = git_sha_or_unknown(repo_root)
    git_worktree_dirty, git_diff_hash = git_worktree_state(repo_root)
    out_dir = prepare_artifact_output_dir(out_dir)

    checks: list[CoreReproductionCheck] = []
    stored_evidence = verify_stored_evidence(
        plan_path,
        out_dir / "stored_evidence",
        repo_root=repo_root,
    )
    (stored_evidence.out_dir / STORED_EVIDENCE_SUMMARY_FILENAME).write_text(
        render_stored_evidence_verification(stored_evidence)
    )
    checks.extend(
        CoreReproductionCheck(
            level=1,
            check_id=check.check_id,
            status=check.status,
            detail=check.detail,
        )
        for check in stored_evidence.checks
    )

    eval_out_dir = out_dir / "eval"
    try:
        with _uv_offline():
            eval_matrix = run_eval_config_all_policies(
                eval_config_path,
                eval_out_dir,
            )
    except (OSError, ValueError) as exc:
        checks.append(
            CoreReproductionCheck(
                level=2,
                check_id="eval.execution",
                status="FAIL",
                detail=f"{type(exc).__name__}: {exc}",
            )
        )
    else:
        checks.append(
            CoreReproductionCheck(
                level=2,
                check_id="eval.execution",
                status="PASS",
                detail=(
                    f"suite={eval_matrix.eval_suite_id}; "
                    f"attempts={sum(len(run.attempts) for run in eval_matrix.policy_runs)}; "
                    f"replays={len(eval_matrix.replay_runs)}"
                ),
            )
        )
        checks.extend(_verify_operational_checks(eval_matrix.out_dir, eval_matrix.config))
        checks.append(_regenerate_eval_report(out_dir, eval_matrix.out_dir))

    result = CoreReproductionResult(
        out_dir=out_dir,
        command=_resolved_command(
            requested_out_dir,
            requested_plan_path,
            requested_eval_config_path,
        ),
        plan_name=plan.name,
        plan_hash=stored_evidence.plan_hash,
        git_sha=git_sha,
        git_worktree_dirty=git_worktree_dirty,
        git_diff_hash=git_diff_hash,
        runtime_provenance=runtime_provenance,
        checks=tuple(checks),
        canonical_artifacts=_canonical_artifact_identities(plan),
        portability_blockers=_detect_portability_blockers(repo_root, plan),
    )
    result.report_path.write_text(render_core_reproduction_report(result))
    return result


def render_core_reproduction_report(result: CoreReproductionResult) -> str:
    passed = sum(check.status == "PASS" for check in result.checks)
    failed = sum(check.status == "FAIL" for check in result.checks)
    runtime = result.runtime_provenance
    lines = [
        "# Core Reproduction Report",
        "",
        f"- Overall: {result.status}",
        f"- Resolved command: `{result.command}`",
        f"- Required checks: PASS={passed}; FAIL={failed}",
        "- Optional levels: SKIP=2",
        "",
        "## Reproduction Levels",
        "",
        "| level | scope | status |",
        "| --- | --- | --- |",
        (
            "| 1 | Validate designated stored training/eval evidence and "
            f"regenerate canonical reports | {result.level_status(1)} |"
        ),
        (
            "| 2 | Execute deterministic controls, scorer, replay, and "
            f"same-run report regeneration | {result.level_status(2)} |"
        ),
        "| 3 | Live model inference | SKIP |",
        "| 4 | Training rerun | SKIP |",
        "",
        "## Invocation Environment",
        "",
        f"- Git SHA: `{result.git_sha}`",
        f"- Git worktree dirty: `{str(result.git_worktree_dirty).lower()}`",
        f"- Git dirty-state hash: `{result.git_diff_hash}`",
        f"- Harness source hash: `{runtime.harness_source_hash}`",
        f"- Harness runtime hash: `{runtime.harness_runtime_hash}`",
        f"- pyproject.toml hash: `{runtime.root_pyproject_hash}`",
        f"- uv.lock hash: `{runtime.root_uv_lock_hash}`",
        (
            f"- Python: `{runtime.python_implementation} "
            f"{runtime.python_version}`"
        ),
        f"- Platform: `{runtime.sys_platform}; {runtime.platform_machine}`",
        "- Dependency execution: `UV_OFFLINE=1` enforced for Level 2",
        "- Docker: not used",
        "",
        "The output-directory argument is invocation-specific. Hashes and statuses "
        "are expected to remain stable only while their authoritative inputs remain "
        "unchanged.",
        "",
        "## Canonical Artifact Identities",
        "",
        f"- Stored-evidence plan: `{result.plan_name}` (`{result.plan_hash}`)",
        "",
        "| kind | name | path | expected hash |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        "| "
        + " | ".join(
            _markdown_cell(value)
            for value in (
                identity.kind,
                identity.name,
                identity.path,
                identity.expected_hash,
            )
        )
        + " |"
        for identity in result.canonical_artifacts
    )
    lines.extend(
        [
            "",
            "## Required Check Results",
            "",
            "| level | check | status | detail |",
            "| --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| {check.level} | {_markdown_cell(check.check_id)} | {check.status} | "
        f"{_markdown_cell(check.detail)} |"
        for check in result.checks
    )
    lines.extend(
        [
            "",
            "## Metadata Ownership",
            "",
            "No global provenance manifest is introduced. Training manifests own "
            "base revision, adapter, input-protocol, training-config, source-data, "
            "seed, trainer-code, runtime, and accelerator identity. Eval and attempt "
            "artifacts own task, scorer/harness, model/provider, decoding, protocol, "
            "and replay identity. This report owns only the composed invocation "
            "status and cites those existing authorities.",
            "",
            "## Failure Injection",
            "",
            "Failure injection is not rerun by this command and is therefore not "
            "reported as a pass here. The focused resume tests separately cover "
            "interruption, missing/corrupt terminal evidence, duplicate ids, model "
            "and scorer timeouts, missing hidden validators, bad config paths, and "
            "semantic-input drift.",
            "",
            "## Portability And Optional Dependencies",
            "",
        ]
    )
    if result.portability_blockers:
        lines.extend(f"- BLOCKER: {blocker}" for blocker in result.portability_blockers)
    else:
        lines.append("- No repository-location blocker was detected for declared inputs.")
    lines.extend(
        [
            "- Live model inference was skipped: no model server, network, or model "
            "download is required by the core command.",
            "- Training reproduction was skipped: no GPU or accelerator runtime is "
            "required by the core command.",
            "",
            "## Supported Claim",
            "",
        ]
    )
    if result.status == "PASS":
        lines.append(
            "At the recorded checkout and artifact location, the designated stored "
            "post-training evidence reconstructs under its pinned manifests, and "
            "the current locked harness executes the deterministic control, hidden-"
            "scorer, replay, artifact, and report path with all required checks passing."
        )
    else:
        lines.append(
            "The combined Level 1 and Level 2 reproduction claim is not supported by "
            "this invocation. Individual passing checks remain diagnostic evidence."
        )
    lines.extend(
        [
            "",
            "## Explicit Non-Claims",
            "",
            "This command does not reproduce live model samples, GPU optimization, "
            "provider scheduling, or human review. It does not inspect heldout-private "
            "outcomes and does not establish model improvement or broad coding-agent "
            "capability. A passing local Level 1 is not a clean-checkout portability "
            "claim while any blockers above remain.",
        ]
    )
    return "\n".join(lines) + "\n"


def _verify_operational_checks(
    eval_out_dir: Path,
    config: EvalConfig,
) -> tuple[CoreReproductionCheck, ...]:
    if not requires_operational_verification(config):
        return (
            CoreReproductionCheck(
                level=2,
                check_id="eval.operational_scope",
                status="FAIL",
                detail="deterministic core config has no controls or configured replay",
            ),
        )
    try:
        verification = verify_eval_suite_operational_expectations(eval_out_dir)
    except (OSError, ValueError) as exc:
        return (
            CoreReproductionCheck(
                level=2,
                check_id="eval.operational_verification",
                status="FAIL",
                detail=f"{type(exc).__name__}: {exc}",
            ),
        )
    return tuple(
        CoreReproductionCheck(
            level=2,
            check_id=check.check_id,
            status=check.status,
            detail=check.detail,
        )
        for check in verification.checks
    )


def _regenerate_eval_report(
    out_dir: Path,
    eval_out_dir: Path,
) -> CoreReproductionCheck:
    generated_report = out_dir / "eval_report.md"
    regenerated_report = out_dir / "eval_report_regenerated.md"
    try:
        write_markdown_report(eval_out_dir, generated_report)
        write_markdown_report(eval_out_dir, regenerated_report)
        generated_hash = hash_file(generated_report)
        regenerated_hash = hash_file(regenerated_report)
        if generated_report.read_bytes() != regenerated_report.read_bytes():
            raise ValueError("same-run regenerated eval report differs")
    except (OSError, ValueError) as exc:
        return CoreReproductionCheck(
            level=2,
            check_id="eval.report_regeneration",
            status="FAIL",
            detail=f"{type(exc).__name__}: {exc}",
        )
    return CoreReproductionCheck(
        level=2,
        check_id="eval.report_regeneration",
        status="PASS",
        detail=(
            f"byte_match=true; generated_hash={generated_hash}; "
            f"regenerated_hash={regenerated_hash}"
        ),
    )


def _canonical_artifact_identities(
    plan: StoredEvidencePlan,
) -> tuple[CanonicalArtifactIdentity, ...]:
    identities = [
        CanonicalArtifactIdentity(
            kind=f"training:{artifact.kind}",
            name=artifact.name,
            path=f"{artifact.artifact_dir}/{MANIFEST_FILENAME}",
            expected_hash=artifact.expected_manifest_hash,
        )
        for artifact in plan.training_artifacts
    ]
    for comparison in plan.comparisons:
        identities.extend(
            (
                CanonicalArtifactIdentity(
                    kind="eval_suite",
                    name=comparison.name,
                    path=f"{comparison.eval_suite_dir}/{MANIFEST_FILENAME}",
                    expected_hash=comparison.expected_suite_manifest_hash,
                ),
                CanonicalArtifactIdentity(
                    kind="canonical_report",
                    name=comparison.name,
                    path=comparison.canonical_report,
                    expected_hash=comparison.expected_report_hash,
                ),
            )
        )
    return tuple(identities)


def _detect_portability_blockers(
    repo_root: Path,
    plan: StoredEvidencePlan,
) -> tuple[str, ...]:
    declared_paths = [
        repo_root / artifact.artifact_dir / MANIFEST_FILENAME
        for artifact in plan.training_artifacts
    ]
    declared_paths.extend(
        repo_root / comparison.eval_suite_dir / MANIFEST_FILENAME
        for comparison in plan.comparisons
    )
    declared_paths.extend(
        repo_root / comparison.canonical_report for comparison in plan.comparisons
    )
    untracked_count = sum(
        not _is_git_tracked(repo_root, path) for path in declared_paths
    )
    absolute_ref_count = sum(
        _count_repo_absolute_refs(repo_root, path)
        for path in declared_paths
        if path.suffix == ".json" and path.is_file()
    )
    blockers: list[str] = []
    if untracked_count:
        blockers.append(
            f"{untracked_count} declared top-level evidence files are not tracked by "
            "Git, so a clean clone does not contain the complete Level 1 input set."
        )
    if absolute_ref_count:
        blockers.append(
            f"declared top-level manifests contain {absolute_ref_count} "
            "repository-owned absolute path references, so the historical evidence "
            "graph is bound to this checkout location."
        )
    return tuple(blockers)


def _is_git_tracked(repo_root: Path, path: Path) -> bool:
    try:
        relative_path = path.resolve().relative_to(repo_root)
    except ValueError:
        return False
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative_path.as_posix()],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _count_repo_absolute_refs(repo_root: Path, path: Path) -> int:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    return sum(
        1
        for value in _walk_json_strings(payload)
        if _is_repo_absolute_path(repo_root, value)
    )


def _walk_json_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(
            item
            for child in value
            for item in _walk_json_strings(child)
        )
    if isinstance(value, dict):
        return tuple(
            item
            for child in value.values()
            for item in _walk_json_strings(child)
        )
    return ()


def _is_repo_absolute_path(repo_root: Path, value: str) -> bool:
    candidate = Path(value)
    if not candidate.is_absolute():
        return False
    try:
        candidate.relative_to(repo_root)
    except ValueError:
        return False
    return True


def _resolved_command(
    out_dir: Path,
    plan_path: Path,
    eval_config_path: Path,
) -> str:
    return shlex.join(
        (
            "uv",
            "run",
            "--offline",
            "--frozen",
            "agentenv",
            "reproduce",
            "core",
            "--out",
            str(out_dir),
            "--plan",
            str(plan_path),
            "--eval-config",
            str(eval_config_path),
        )
    )


@contextmanager
def _uv_offline() -> Iterator[None]:
    previous = os.environ.get("UV_OFFLINE")
    os.environ["UV_OFFLINE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("UV_OFFLINE", None)
        else:
            os.environ["UV_OFFLINE"] = previous


def _resolve_input_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
