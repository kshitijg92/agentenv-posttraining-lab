# Week 3 Implementation Notes

## 2026-06-20

### Decision

Use `AttemptStatus` as the single canonical outcome vocabulary for now, instead
of adding a separate failure-label layer.

### Reasoning

The current system is small enough that a second label layer would add more
translation surface than value. The scorer-audit cases can compare expected and
actual attempt statuses directly.

Richer statuses such as `INVALID_SHORTCUT` and
`HIDDEN_VALIDATOR_ACCESS_ATTEMPT` should only be added when the harness has
specific detection evidence.

### Shipped

- Added `docs/attempt_status_taxonomy.md`.
- Updated the Week 3 plan to use attempt statuses instead of failure labels.

### Self-Deception Trap

Do not add expressive statuses just because they are useful for reports. If the
harness cannot justify a status from artifacts or explicit checks, it should
remain a note or manual review finding.

### Decision

Unexpected exceptions inside `run_patch_attempt(...)` should surface as
`ORCHESTRATOR_ERROR` attempt results instead of escaping the attempt path.

### Reasoning

Week 3 is about measurement trust. If a harness bug or workspace-preparation
issue escapes as an uncaught exception, the attempt may fail without a normal
status or artifact bundle. That makes control runs and scorer-audit reports
harder to interpret.

The attempt result now records only the exception class name in `error_class`.
That keeps the status contract simple while still separating harness failure
from task-solution failure.

The debug evidence lives in a separate `error.txt` artifact. Subprocess stdout
and stderr remain command-output artifacts; Python harness exceptions should not
be mixed into them.

### Shipped

- Added a generic exception handler in `run_patch_attempt(...)`.
- Added in-memory `AttemptErrorDetails` with exception class, message, and
  traceback.
- Added persistent `error.txt` attempt artifacts.
- Added a focused test that forces workspace preparation to raise and expects
  `ORCHESTRATOR_ERROR`.

### Ran

```bash
uv run pytest tests/test_attempt.py tests/test_attempt_io.py
uv run ruff check src/agentenv/orchestrators/attempt.py src/agentenv/orchestrators/attempt_io.py tests/test_attempt.py tests/test_attempt_io.py
uv run pytest
uv run ruff check .
uv run pyright
```

### Result

- `tests/test_attempt.py` and `tests/test_attempt_io.py` passed.
- Full `pytest` passed.
- Ruff passed for touched Python files and for the full repo.
- `pyright` did not run cleanly because it could not resolve third-party imports
  such as `pydantic`, `pytest`, `typer`, and `xxhash`, even though `uv run
  python -c "import ..."` resolved those imports. This appears to be pyright
  interpreter/environment resolution rather than a runtime failure from this
  change.

### Debugging Invariant

Every persisted `ORCHESTRATOR_ERROR` should include enough evidence to debug the
harness failure without rerunning:

- `attempt.json` records `status=ORCHESTRATOR_ERROR`.
- `attempt.json` records the compact `error_class`.
- `error.txt` records exception class, message, and traceback.
- `trace.jsonl` references `error.txt` from the terminal attempt event.

The normal success path still writes `error.txt`, but it is empty.

### Next Small Step

Decide the narrow detection rule for `INVALID_SHORTCUT` before adding it to the
runtime status set.
