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
