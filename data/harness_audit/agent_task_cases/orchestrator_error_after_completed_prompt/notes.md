# Orchestrator Error After Completed Prompt Agent Task Audit

This case verifies the boundary between a completed prompt loop and the outer
agent task orchestrator.

The scripted fake model replaces the public test with a passing test that writes
non-UTF-8 bytes into `src/mathlib.py`, runs the public check, then emits
`final_answer`. The prompt loop should complete with no prompt-loop error. When
the agent task orchestrator tries to render the workspace diff into a candidate
patch, reading `src/mathlib.py` should raise `UnicodeDecodeError`. The agent task
run should report `orchestrator_error`, and no nested scorer attempt should run.
