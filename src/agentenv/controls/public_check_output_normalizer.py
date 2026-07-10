import re
from pathlib import Path

from agentenv.controls.public_check_idempotency_schema import (
    PublicCheckOutputNormalizationContext,
)
from agentenv.hashing import hash_file, hash_json


PUBLIC_CHECK_OUTPUT_NORMALIZER_VERSION = "public_check_output_normalizer_v0"
WORKSPACE_PLACEHOLDER = "<WORKSPACE>"
RUNNER_TEMP_PLACEHOLDER = "<RUNNER_TEMP>"
DURATION_PLACEHOLDER = "<DURATION>"

_SECONDS_DURATION_RE = re.compile(r"\bin \d+(?:\.\d+)?s\b")
_MILLISECONDS_DURATION_RE = re.compile(r"\bin \d+ms\b")


def compute_public_check_output_normalizer_code_hash() -> str:
    return hash_file(Path(__file__))


def normalize_public_check_output(
    text: str,
    context: PublicCheckOutputNormalizationContext,
) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    replacements = sorted(
        (
            (context.workspace_root, WORKSPACE_PLACEHOLDER),
            (context.runner_temp_root, RUNNER_TEMP_PLACEHOLDER),
        ),
        key=lambda replacement: len(replacement[0]),
        reverse=True,
    )
    for source, placeholder in replacements:
        normalized = _replace_path_root(normalized, source, placeholder)
    normalized = _SECONDS_DURATION_RE.sub(
        f"in {DURATION_PLACEHOLDER}",
        normalized,
    )
    return _MILLISECONDS_DURATION_RE.sub(
        f"in {DURATION_PLACEHOLDER}",
        normalized,
    )


def _replace_path_root(text: str, source: str, placeholder: str) -> str:
    path_token_character = r"[\w.~+-]"
    pattern = re.compile(
        rf"(?<!{path_token_character}){re.escape(source)}"
        rf"(?!{path_token_character})"
    )
    return pattern.sub(placeholder, text)


def hash_normalized_public_check_result(
    *,
    exit_code: int,
    stdout: str,
    stderr: str,
    context: PublicCheckOutputNormalizationContext,
) -> str:
    return hash_json(
        {
            "exit_code": exit_code,
            "stdout": normalize_public_check_output(stdout, context),
            "stderr": normalize_public_check_output(stderr, context),
        }
    )
