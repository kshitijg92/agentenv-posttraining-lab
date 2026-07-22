#!/usr/bin/env python3
"""Generate a deterministic unified-diff scorer control from source snapshots."""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path


def generate_patch(*, task_dir: Path, solution_dir: Path, output: Path) -> None:
    seed_dir = (task_dir / "seed_workspace").resolve()
    solution_dir = solution_dir.resolve()
    chunks: list[str] = []
    solution_paths = sorted(path for path in solution_dir.rglob("*") if path.is_file())
    if not solution_paths:
        raise ValueError(f"solution directory contains no files: {solution_dir}")

    for solution_path in solution_paths:
        relative_path = solution_path.relative_to(solution_dir)
        seed_path = seed_dir / relative_path
        if not seed_path.is_file():
            raise ValueError(f"solution has no seed counterpart: {relative_path}")
        seed_lines = seed_path.read_text().splitlines(keepends=True)
        solution_lines = solution_path.read_text().splitlines(keepends=True)
        chunks.extend(
            difflib.unified_diff(
                seed_lines,
                solution_lines,
                fromfile=f"a/{relative_path.as_posix()}",
                tofile=f"b/{relative_path.as_posix()}",
            )
        )

    if not chunks:
        raise ValueError("solution snapshots do not differ from the seed workspace")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(chunks))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--solution-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate_patch(
        task_dir=args.task_dir,
        solution_dir=args.solution_dir,
        output=args.output,
    )


if __name__ == "__main__":
    main()
