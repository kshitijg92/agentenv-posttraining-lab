# Completed No Final Newline Agent Task Audit

This case audits a harness boundary observed during local Qwen smoke evaluation.

The scripted fake model lists files, reads `src/mathlib.py`, writes the correct
solution without a final newline, uses an arbitrary `ValueError` message, runs
the public tests, and returns a final answer. The agent loop should complete,
the nested scorer should receive a valid candidate patch, and public plus hidden
checks should pass.

This case protects against regressions where the harness generates a corrupt
unified diff from a valid workspace edit.
