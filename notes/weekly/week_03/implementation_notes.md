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

### Decision

Remove `SCORER_ERROR` from the active `AttemptStatus` vocabulary for now.

### Reasoning

The code did not produce `SCORER_ERROR`. Hidden-test assertion failures were
already represented by `HIDDEN_TEST_FAIL`, while exceptions raised around the
hidden scorer would now be caught as `ORCHESTRATOR_ERROR`.

Keeping an unused `SCORER_ERROR` would imply a scorer infrastructure boundary
that the harness does not actually distinguish. If we later split scorer errors
from public-check errors and other harness failures, that should come with
specific exception handling and tests.

### Shipped

- Removed `SCORER_ERROR` from `AttemptStatus`.
- Updated `docs/attempt_status_taxonomy.md` to say scorer infrastructure
  failures currently fall under `ORCHESTRATOR_ERROR`.

### Decision

Detect one concrete invalid shortcut this week: a submitted patch that modifies
public tests under `tests/`.

### Reasoning

Changing public tests is a scoring-contract violation, not merely a wrong
solution. There is no point in running public checks after the patch has changed
the checks themselves. The attempt should stop immediately after patch
application and record a terminal `INVALID_SHORTCUT` status.

This keeps `HIDDEN_TEST_FAIL` for patches that leave the public checks intact
but fail hidden behavior.

### Shipped

- Added `INVALID_SHORTCUT` to `AttemptStatus`.
- Added a post-patch, pre-public-check detector for changed files under
  `tests/`.
- Added a focused test that modifies `tests/test_public.py` and verifies that
  only the patch-apply phase runs.

### Next Small Step

Decide whether `HIDDEN_VALIDATOR_ACCESS_ATTEMPT` should initially inspect only
submitted patch text, or whether it should also inspect command traces and final
diffs.
