from pathlib import Path

import agentenv.controls.public_check_output_normalizer as normalizer_module
from agentenv.controls.public_check_idempotency_schema import (
    PublicCheckOutputNormalizationContext,
)
from agentenv.controls.public_check_output_normalizer import (
    DURATION_PLACEHOLDER,
    PUBLIC_CHECK_OUTPUT_NORMALIZER_VERSION,
    RUNNER_TEMP_PLACEHOLDER,
    WORKSPACE_PLACEHOLDER,
    compute_public_check_output_normalizer_code_hash,
    hash_normalized_public_check_result,
    normalize_public_check_output,
)
from agentenv.hashing import hash_file


def _context(
    *,
    workspace_root: str = "/tmp/calibration/workspace",
    runner_temp_root: str = "/tmp/calibration-command-temp",
) -> PublicCheckOutputNormalizationContext:
    return PublicCheckOutputNormalizationContext(
        workspace_root=workspace_root,
        runner_temp_root=runner_temp_root,
    )


def test_normalizer_canonicalizes_crlf_and_bare_cr() -> None:
    normalized = normalize_public_check_output(
        "first\r\nsecond\rthird\n",
        _context(),
    )

    assert normalized == "first\nsecond\nthird\n"


def test_normalizer_replaces_only_runner_supplied_path_roots() -> None:
    context = _context()
    normalized = normalize_public_check_output(
        (
            f"{context.workspace_root}/src/module.py\n"
            f"{context.runner_temp_root}/pytest/output.txt\n"
            f"{context.workspace_root}-sibling/src/module.py\n"
            "/tmp/unowned/output.txt\n"
        ),
        context,
    )

    assert normalized == (
        f"{WORKSPACE_PLACEHOLDER}/src/module.py\n"
        f"{RUNNER_TEMP_PLACEHOLDER}/pytest/output.txt\n"
        f"{context.workspace_root}-sibling/src/module.py\n"
        "/tmp/unowned/output.txt\n"
    )


def test_normalizer_replaces_known_duration_fragments() -> None:
    normalized = normalize_public_check_output(
        "1 passed in 0.12s\nsetup completed in 8s\ncommand finished in 15ms\n",
        _context(),
    )

    assert normalized == (
        f"1 passed in {DURATION_PLACEHOLDER}\n"
        f"setup completed in {DURATION_PLACEHOLDER}\n"
        f"command finished in {DURATION_PLACEHOLDER}\n"
    )


def test_normalizer_preserves_trailing_whitespace_and_final_newline() -> None:
    context = _context()

    assert normalize_public_check_output("value  \n", context) == "value  \n"
    assert normalize_public_check_output("value", context) == "value"


def test_normalized_result_hash_matches_across_known_volatile_values() -> None:
    first_context = _context()
    second_context = _context(
        workspace_root="/var/tmp/second/workspace",
        runner_temp_root="/var/tmp/second-command-temp",
    )

    first_hash = hash_normalized_public_check_result(
        exit_code=0,
        stdout=(
            f"loaded {first_context.workspace_root}/src/module.py\r\n"
            "1 passed in 0.12s\r\n"
        ),
        stderr=f"cache: {first_context.runner_temp_root}/pytest\r\n",
        context=first_context,
    )
    second_hash = hash_normalized_public_check_result(
        exit_code=0,
        stdout=(
            f"loaded {second_context.workspace_root}/src/module.py\n"
            "1 passed in 8.4s\n"
        ),
        stderr=f"cache: {second_context.runner_temp_root}/pytest\n",
        context=second_context,
    )

    assert first_hash == second_hash


def test_normalized_result_hash_changes_for_meaningful_output() -> None:
    context = _context()
    baseline = hash_normalized_public_check_result(
        exit_code=0,
        stdout="value=1\n",
        stderr="",
        context=context,
    )

    assert hash_normalized_public_check_result(
        exit_code=0,
        stdout="value=2\n",
        stderr="",
        context=context,
    ) != baseline
    assert hash_normalized_public_check_result(
        exit_code=1,
        stdout="value=1\n",
        stderr="",
        context=context,
    ) != baseline
    assert hash_normalized_public_check_result(
        exit_code=0,
        stdout="value=1",
        stderr="",
        context=context,
    ) != baseline
    assert hash_normalized_public_check_result(
        exit_code=0,
        stdout="value=1  \n",
        stderr="",
        context=context,
    ) != baseline


def test_normalized_result_hash_keeps_stdout_and_stderr_boundaries() -> None:
    context = _context()

    assert hash_normalized_public_check_result(
        exit_code=0,
        stdout="ab",
        stderr="c",
        context=context,
    ) != hash_normalized_public_check_result(
        exit_code=0,
        stdout="a",
        stderr="bc",
        context=context,
    )


def test_normalizer_version_and_code_hash_are_pinned() -> None:
    assert PUBLIC_CHECK_OUTPUT_NORMALIZER_VERSION == (
        "public_check_output_normalizer_v0"
    )
    module_path = Path(normalizer_module.__file__)
    assert compute_public_check_output_normalizer_code_hash() == hash_file(module_path)
