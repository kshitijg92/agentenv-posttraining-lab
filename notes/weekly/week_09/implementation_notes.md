# Week 9 Implementation Notes

## 2026-07-09

### Training-Eligibility Authority

#### Decision

When the schemas are revised, `TrainingCandidateRecord` will be the first and
only artifact that owns downstream-use decisions such as positive SFT,
negative-example, and preference-data eligibility.

`TrajectoryRecord` will retain source evidence and versioned derived
assessments, including reward and leakage evidence, but it will not own
training-use permission. Constructed dataset records will own the exact repair,
serialization, loss mask, or preference-pair transformation applied after
eligibility is decided.

#### Reasoning

The current implementation has both preliminary eligibility on
`TrajectoryRecord` and final eligibility on `TrainingCandidateRecord`. That
creates two authorities that can drift or disagree. Week 9 introduces the
candidate/data-contract boundary, so it is the appropriate point to remove the
duplicated decision instead of adding compatibility shims.

#### Status

Design decision only. No schema or builder migration has been implemented yet.

### Public-Check Repeatability And Workspace State

#### Decision

Add a required, non-defaulted field to every `PublicCheck`:

```text
are_tests_idempotent: bool
```

`true` declares that the check is expected to preserve canonical workspace
state and produce a repeat-stable normalized observation. `false` prevents
repeated `run_tests` calls from being classified as mechanically redundant.
Omitting the field is a task-manifest validation error.

Public-check idempotence will be defined against the repo's canonical workspace
hash rather than a literal hash of every generated filesystem byte. The
canonical boundary excludes declared noisy paths such as `.pytest_cache` and
`__pycache__`. If those exclusions become brittle or exploitable, the fallback
is to suppress cache generation and narrow the ignored surface.

A normally completed public check produces a valid observation whether its
validator outcome is PASS or FAIL. An immediate identical repeat can therefore
be mechanically redundant after either outcome when the check is calibrated as
repeat-stable and state-preserving. Timeouts and tool-execution errors do not
receive that treatment because they did not produce a trusted observation.

Control flake detection is the intended calibration surface for the public
check's repeatability declaration. The proposed evidence is:

```text
canonical workspace hash before first check
    == canonical workspace hash after first check
    == canonical workspace hash after immediate repeat

normalized first result == normalized repeated result
```

#### Limitation

Control calibration exercises known task states; it does not prove behavior on
every model-generated workspace. Mutations under excluded noisy paths are also
outside the canonical-state guarantee.

#### Open Design Questions

- Decide whether actual model `run_tests` calls also persist before/after
  canonical workspace hashes.
- Define the normalized result hash used for repeat comparison.

#### Status

The required `PublicCheck.are_tests_idempotent` field is implemented. All four
current task manifests explicitly declare `true`, and a focused regression test
proves that omission fails manifest validation.

Repeatability calibration, control-flake integration, tool-result changes, and
redundant-block detection are not implemented yet.

Adding the required field intentionally changes every task-manifest hash.
Existing Qwen and trajectory artifacts remain historical evidence for the old
task inputs; a new pipeline requiring idempotence calibration must not silently
treat those hashes as current.

Verification:

```text
task-manifest tests: 12 passed
task-pack validation: valid, 4 tasks
focused Ruff: passed
Pyright: passed
git diff --check: passed
full parallel suite: 709 passed
```

### Control Calibration Is A Hard Training-Candidate Gate

#### Decision

Training-candidate export must fail closed when its required control-calibration
evidence is missing, hash-mismatched, incomplete, or failed. It must not emit
analysis-only candidate rows as a fallback.

At that point the harness measurement is not trusted. The correct workflow is
to inspect the control-calibration failures, repair the task or harness, and
rerun calibration before constructing any post-training candidates.

The candidate export should pin the trusted control-calibration artifact once
in its manifest rather than duplicate suite-level evidence into every source
trajectory.

#### Reasoning

Analysis-only is a valid data-use outcome for a trustworthy trajectory that is
not eligible for training. It is not an escape hatch for an untrusted
measurement system. Emitting candidate records after the calibration gate
fails would give downstream consumers structured data whose task outcomes
cannot be believed.

#### Status

Design decision only. The current training-candidate export does not yet accept
or validate control-calibration evidence.

### Mechanical-Redundancy Assessment Placement

#### Decision

Do not add a trusted mechanical-redundancy conclusion directly to
`TrajectoryRecord`. The trajectory already preserves raw assistant tool calls
and tool results, but it does not carry the suite-level control-calibration
evidence required to trust an idempotence-based conclusion.

Training-candidate construction will join:

```text
trajectory tool-call and tool-result evidence
task-manifest idempotence declaration
trusted control-calibration evidence
```

It will detect redundant blocks and store the resulting structured assessment
on `TrainingCandidateRecord`, alongside the downstream-use decisions owned by
that record.

#### Status

Placement is decided. The redundant-block assessment schema and detector remain
to be designed.

### Public-Check Idempotence Calibration Statuses

#### Decision

Represent each invocation with a nested `SinglePublicCheckRun` rather than
parallel lists of workspace hashes and outcomes. Each run will pair its
before/after canonical workspace hashes with the observation produced by that
invocation.

The per-run execution statuses are:

```text
COMPLETED
TIMEOUT
RUNNER_FAILURE
```

`COMPLETED` means the command returned normally; the public validator may still
have passed or failed. `TIMEOUT` means the command did not return within its
budget. `RUNNER_FAILURE` is reserved for an unexpected failure in the
low-level command execution or result-collection path. Do not use
`ORCHESTRATION_FAILURE`, which belongs to the broader attempt lifecycle.

The top-level calibration statuses are:

```text
IDEMPOTENT
NON_IDEMPOTENT
INCONCLUSIVE
```

Derive them with this precedence:

```text
observed canonical-state or normalized-result drift -> NON_IDEMPOTENT
otherwise, any timeout or runner failure            -> INCONCLUSIVE
otherwise                                           -> IDEMPOTENT
```

The precedence prevents a later infrastructure failure from erasing a
non-idempotence violation already observed.

Do not serialize a separate freely assignable `idempotent: bool`. It would
duplicate the authoritative status and could contradict it. Code may expose a
derived convenience property with these semantics:

```text
IDEMPOTENT      -> true
NON_IDEMPOTENT  -> false
INCONCLUSIVE    -> none
```

Only `IDEMPOTENT` satisfies the hard candidate-export gate for a public check
whose task-manifest declaration is `are_tests_idempotent: true`.

For a completed run, do not reuse attempt-level or validator-level status
fields. Idempotence is based only on canonical state preservation and command
observation equivalence. The normalized command observation consists of:

```text
exit code
normalized stdout
normalized stderr
```

Raw stdout and stderr will be persisted as separate artifact files and
referenced from `SinglePublicCheckRun` with relative, content-hash-pinned
artifact references. Do not embed unbounded command output directly in the run
record. This keeps record size bounded for future checks with large output.

The raw artifact content hashes prove file integrity. A separate normalized
result hash, derived from exit code plus normalized stdout and stderr, supports
repeat comparison while excluding volatile values such as durations and
temporary paths. Duration may be retained for diagnostics but must not
contribute to the normalized result hash.

For `TIMEOUT` and `RUNNER_FAILURE`, persist partial stdout and stderr as
hash-pinned artifact files whenever the command runner captured them. The
references are optional because some failures occur before either stream
exists. Partial failure output is diagnostic evidence only: it must not produce
a normalized completed-result hash or participate in the equality comparison
used to establish idempotence.

Model a single run as a discriminated union rather than one object with many
nullable fields:

```text
CompletedPublicCheckRun:
    status: COMPLETED

FailedPublicCheckRun:
    status: FAILURE
    failure_mode: TIMEOUT | RUNNER_FAILURE

SinglePublicCheckRun = CompletedPublicCheckRun | FailedPublicCheckRun
```

Every failed run requires both a typed `error_class` and a non-empty,
human-readable `error_message`, following the repo's existing result-schema
discipline. Completed runs forbid failure mode and error fields. The stable
failure mode supports aggregation; error class and message preserve diagnostic
specificity.

Identify one calibrated public check with:

```text
task manifest hash
public check list index
exact command
```

Do not add a separate `PublicCheck.id` in v0. The manifest hash pins the exact
ordered public-check list, the index disambiguates entries within that version,
and the command makes the reference human-auditable. Reordering or changing a
check intentionally changes the manifest hash and invalidates the old
calibration; identity does not need to remain stable across task-manifest
versions.

The number of consecutive same-workspace executions used for one idempotence
calibration is configurable, defaults to `2`, and must be at least `2`. Persist
the effective repeat count in the calibration artifact and require run indexes
to cover the full ordered range without gaps or duplicates.

This is conceptually distinct from the existing control-run `repeats` value,
which counts fresh whole-control attempts. Give consecutive public-check
idempotence runs their own CLI option rather than silently using one value for
both axes. The exact option name remains an implementation naming decision.

Calibrate each public check on its own fresh copy of `seed_workspace`. Do not
apply an oracle patch, known-bad patch, or model patch. Repeated executions for
that check share the one calibration workspace, but separate public checks do
not share a workspace. Hidden validators and control assets remain outside the
prepared workspace.

Seed-only calibration proves repeatability only on the seed state. It does not
prove that arbitrary model-generated code cannot cause the check to mutate
canonical workspace state. Therefore, actual model `run_tests` executions will
also record canonical workspace hashes before and after the call. Redundancy
assessment can then validate state preservation on the actual trajectory rather
than relying only on the seed calibration declaration.

These runtime hashes are evaluator evidence and must not be added to the
model-visible tool observation.

Persist them on every `ToolResult`, not only `run_tests` results:

```text
arguments_hash
canonical_workspace_hash_before
canonical_workspace_hash_after
```

Rename the existing `input_hash` field to `arguments_hash`. Do not add a
backward-compatible alias; this learning lab intentionally prefers a clean
current contract over compatibility with historical prompt-loop artifacts.

For valid calls, hash canonical validated arguments so omitted defaults and
explicit default values represent the same semantic input. Invalid calls may
hash the raw attempted arguments, but they are not eligible for mechanical
redundancy conclusions.

Require both canonical workspace hashes for every tool result, including
read-only tools, rejected calls, timeouts, and errors. This detects accidental
state mutation in implementations such as `read_file`, and proves that a
rejected call did not alter workspace state. The overhead is acceptable for the
small learning-lab workspaces.

Define canonical workspace state from a sorted sequence of included regular-file
records containing:

```text
workspace-relative path
exact file contents
```

Both path and contents must contribute. Content alone would miss semantically
important renames and the addition or removal of empty files such as
`__init__.py`. Continue excluding declared noisy paths. Do not include
timestamps, ownership, permissions, or symlink metadata in the v0 guarantee.
Use an unambiguous structured encoding so file boundaries cannot collide.

Keep both hashes out of model-visible tool-message content and metadata. Add a
regression test for that boundary when the fields are implemented.

If either required canonical workspace hash cannot be computed, do not emit an
incomplete `ToolResult`. Raise a typed harness/instrumentation failure and
terminate the attempt through the orchestrator-error path. Hash availability is
part of the measurement contract, so a normal model/tool outcome cannot be
reported without it.

The current prompt loop lets unexpected tool-execution exceptions propagate to
`run_agent_task_attempt`, which maps them to `AgentTaskRunStatus` value
`orchestrator_error`.

Change that boundary so a workspace-hash failure after prior turns preserves a
partial prompt-loop artifact containing the messages, model responses, and
valid tool results recorded before the failure. The failed call itself must not
create a `ToolResult`; its typed error class and message belong to the terminal
prompt-loop result. The enclosing agent task run must still classify the
outcome as an orchestrator/harness failure rather than a model failure.

Use `PromptLoopStatus` value `orchestrator_error` for this preserved harness
failure. The enclosing `AgentTaskRunStatus` is also `orchestrator_error`, while
the typed `error_class` identifies the specific cause such as workspace-state
hashing failure. Do not introduce the redundant status name
`prompt_loop_orchestration_error`; the containing `PromptLoopResult` already
provides that scope.

An orchestrator failure before prompt-loop construction has
`prompt_loop_status=None`. A failure caught inside the prompt loop has
`prompt_loop_status=orchestrator_error` and preserves the partial prompt-loop
artifact.

#### Status

Design decision only. Calibration schemas and runtime behavior are not yet
implemented.

### Canonical Workspace Hash Helper

#### Implementation

Added the shared `agentenv.hashing.hash_directory` helper. It hashes a
structured, sorted list of workspace-relative paths and exact per-file content
hashes, reusing the existing noisy-path exclusions. It rejects missing and
non-directory roots rather than giving them the same hash as an empty
workspace.

Task hashing now delegates its directory hashing to the shared helper, removing
the private duplicate implementation without changing the intended task-hash
contract.

Focused tests cover:

```text
identical state with different file-creation order
file-content mutation
file rename, addition, and deletion
empty-file addition and removal
noisy-path exclusion
missing and non-directory root rejection
```

#### Verification

```text
focused hashing and task-hashing tests: 17 passed
focused Ruff: passed
focused Pyright: passed
full parallel suite: 715 passed, 2 nested audit/report failures
isolated sequential rerun of both failures: 2 passed
```

The two parallel failures are the same resource-sensitive nested audit tests
previously observed under 16-worker execution; both pass outside that
contention. This run is not recorded as a clean full-suite pass.
