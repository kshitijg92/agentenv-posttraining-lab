#!/usr/bin/env python3
"""Generate standard agent controls from a task's oracle patch.

This is an authoring helper, not part of eval execution. It applies the oracle
patch to a temporary copy of the seed workspace, then emits deterministic
write-file controls containing the resulting source bytes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


PUBLIC_TEST_COMMAND = "uv run --quiet --frozen pytest tests/test_public.py"


def _action(**payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _tool_step(tool_name: str, arguments: dict[str, object]) -> dict[str, str]:
    return {
        "output_text": _action(
            action="tool_call",
            tool_name=tool_name,
            arguments=arguments,
        )
    }


def _changed_paths(patch_path: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for line in patch_path.read_text().splitlines():
        if not line.startswith("+++ b/"):
            continue
        path = line.removeprefix("+++ b/")
        if path not in paths:
            paths.append(path)
    if not paths:
        raise ValueError(f"oracle patch changes no b/ paths: {patch_path}")
    return tuple(paths)


def _expected_tool_result(tool_name: str, status: str, **extra: str) -> dict[str, str]:
    return {"tool_name": tool_name, "status": status, **extra}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def generate_controls(task_dir: Path) -> None:
    task_dir = task_dir.resolve()
    seed_dir = task_dir / "seed_workspace"
    patch_path = task_dir / "controls/scorer_control_patches/oracle.patch"
    controls_dir = task_dir / "controls/agent_control_scripts"
    controls_dir.mkdir(parents=True, exist_ok=True)
    changed_paths = _changed_paths(patch_path)

    with tempfile.TemporaryDirectory(prefix="agentenv-control-authoring-") as raw_tmp:
        solved_dir = Path(raw_tmp) / "workspace"
        shutil.copytree(seed_dir, solved_dir)
        subprocess.run(
            ["patch", "-p1", "--batch", "--forward", "-i", str(patch_path)],
            cwd=solved_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        solved_contents = {
            path: (solved_dir / path).read_text() for path in changed_paths
        }

    inspect_steps = [_tool_step("list_files", {"path": "src"})]
    inspect_steps.extend(
        _tool_step("read_file", {"path": path}) for path in changed_paths
    )
    write_steps = [
        _tool_step("write_file", {"path": path, "content": solved_contents[path]})
        for path in changed_paths
    ]
    finish_steps = [
        _tool_step("run_tests", {"command": PUBLIC_TEST_COMMAND}),
        {"output_text": _action(action="final_answer", text="done")},
    ]

    happy = {
        "schema_version": "agent_control_script_v0",
        "script": {"steps": inspect_steps + write_steps + finish_steps},
        "expected_result": {"prompt_loop_status": "completed"},
    }
    _write_json(controls_dir / "happy_path.json", happy)

    malformed = {
        "schema_version": "agent_control_script_v0",
        "script": {
            "steps": [
                {
                    "output_text": (
                        "{\"action\":\"tool_call\",,\"tool_name\":"
                        f"\"read_file\",\"arguments\":{{\"path\":"
                        f"\"{changed_paths[0]}\"}}}}"
                    )
                }
            ]
        },
        "expected_result": {"prompt_loop_status": "invalid_model_output"},
    }
    _write_json(controls_dir / "malformed_json.json", malformed)

    recoverable_steps = [_tool_step("read_file", {})] + inspect_steps + write_steps + finish_steps
    expected_tool_results = [
        _expected_tool_result(
            "read_file",
            "error",
            error_class="InvalidToolInput",
        ),
        _expected_tool_result("list_files", "ok"),
    ]
    expected_tool_results.extend(
        _expected_tool_result("read_file", "ok") for _ in changed_paths
    )
    expected_tool_results.extend(
        _expected_tool_result("write_file", "ok") for _ in changed_paths
    )
    expected_tool_results.append(_expected_tool_result("run_tests", "ok"))
    recoverable = {
        "schema_version": "agent_control_script_v0",
        "script": {"steps": recoverable_steps},
        "expected_result": {
            "prompt_loop_status": "completed",
            "tool_results": expected_tool_results,
        },
    }
    _write_json(
        controls_dir / "bad_tool_input_then_recovery.json",
        recoverable,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    for task_dir in args.task_dirs:
        generate_controls(task_dir)


if __name__ == "__main__":
    main()
