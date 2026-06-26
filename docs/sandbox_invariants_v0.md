# Sandbox Invariants v0

This document records the current local workspace invariants for the eval lab.
It describes what the harness enforces today, not a production hostile-code
sandbox.

## Invariant 1: Hidden Validators Are Not Agent-Visible

Hidden validators must exist in the task package, but must not be present inside
the prepared agent workspace.

For the current local repo environment:

```text
task package
  task.yaml
  seed_workspace/
  hidden_tests/
  controls/

prepared agent workspace
  copied from seed_workspace/
  must not contain hidden_tests/
```

## Why This Matters

Hidden validators are the measurement instrument. If a submitted patch can read
or modify them during the agent phase, hidden scoring stops measuring
generalization and starts measuring leakage or reward hacking.

## Current Enforcement

`prepare_agent_workspace(...)` copies only the task's `seed_workspace/` into a
fresh workspace. It then checks every manifest-declared hidden validator path and
raises if that path exists inside the prepared workspace.

Current test evidence:

```text
tests/sandbox/test_invariants.py::test_hidden_validators_are_not_present_in_prepared_agent_workspace
```

## Invariant 2: Control Patches Are Not Agent-Visible

Control patches must exist in the task package, but must not be present inside
the prepared agent workspace.

For the current local repo environment:

```text
task package
  task.yaml
  seed_workspace/
  hidden_tests/
  controls/

prepared agent workspace
  copied from seed_workspace/
  must not contain controls/
```

## Why This Matters

Controls are calibration assets. If a submitted patch can read the oracle or
known-bad controls during the agent phase, it can copy the oracle solution,
infer hidden behavior, or game the control assumptions.

## Current Enforcement

`prepare_agent_workspace(...)` copies only the task's `seed_workspace/` into a
fresh workspace. Since controls live outside `seed_workspace/`, they are not
copied into the prepared agent workspace.

Current test evidence:

```text
tests/sandbox/test_invariants.py::test_control_patches_are_not_present_in_prepared_agent_workspace
```

## Invariant 3: Each Attempt Starts From A Fresh Workspace Seed Copy

Each attempt must start from a fresh copy of `seed_workspace`.

Mutating one prepared workspace must not mutate `seed_workspace` or any later
prepared workspace.

For the current local repo environment:

```text
seed_workspace/
  source of truth for each attempt workspace

prepared workspace A
  copied from seed_workspace/
  may be mutated by patch application and checks

prepared workspace B
  copied independently from seed_workspace/
  must not inherit mutations from workspace A
```

## Why This Matters

Repeated evals and control runs are only meaningful if one attempt cannot
contaminate the next. Otherwise a later attempt could inherit files, edits,
caches, or damage from an earlier attempt, making repeated results misleading.

## Current Enforcement

`prepare_agent_workspace(...)` uses `shutil.copytree(...)` to create a new
workspace directory from `seed_workspace/` for each prepared workspace.

Current test evidence:

```text
tests/sandbox/test_invariants.py::test_mutating_one_prepared_workspace_does_not_mutate_seed_or_later_workspace
```

## Invariant 4: Leakage Canary Is Not Agent-Visible

The task leakage canary must not appear in the prepared agent workspace or in
agent-visible attempt artifacts.

For the current local repo environment:

```text
task.yaml
  leakage_canary: private marker for leakage checks

prepared agent workspace
  must not contain leakage_canary in file contents

attempt artifacts
  every generated file under the attempt artifact directory
  must not contain leakage_canary
```

## Why This Matters

The leakage canary is a private marker used to detect hidden-information access.
If it appears in the prepared workspace or persisted attempt artifacts, the lab
has created a path for private task information to leak into agent-visible or
operator-visible evidence.

## Current Enforcement

The canary is stored in `task.yaml`, which is not copied into the prepared
workspace. Attempt artifacts record task and submission paths, command metadata,
status fields, streams, errors, and diffs, but not task manifest contents.

Current test evidence:

```text
tests/sandbox/test_invariants.py::test_leakage_canary_is_absent_from_workspace_and_attempt_artifacts
```

## Invariant 5: Task Manifest Contents Are Not Agent-Visible

The task manifest file and manifest contents must not be present inside the
prepared agent workspace.

Attempt artifacts may record `task_manifest_path` for provenance, but must not
embed `task.yaml` contents.

For the current local repo environment:

```text
task.yaml
  private task metadata
  hidden validator paths
  control patch paths
  leakage canary

prepared agent workspace
  copied from seed_workspace/
  must not contain task.yaml
  must not contain task manifest contents

attempt artifacts
  may contain task_manifest_path
  every generated file under the attempt artifact directory
  must not embed task.yaml contents
```

## Why This Matters

The manifest is a harness contract, not an agent input. It includes private
measurement metadata such as hidden-validator paths, control patch paths, and
the leakage canary. Exposing the manifest contents would weaken hidden
validation and control calibration.

## Current Enforcement

`prepare_agent_workspace(...)` copies only `seed_workspace/`, not `task.yaml`.
Attempt artifacts keep path provenance for debugging and replay, but do not
serialize the task manifest body.

Current test evidence:

```text
tests/sandbox/test_invariants.py::test_task_manifest_contents_are_absent_from_workspace_and_attempt_artifacts
```

## Invariant 6: Deterministic Control Repeats Are Stable

For deterministic control patches, repeated attempts must produce stable
`attempt_status`, `public_status`, `hidden_status`, and `final_diff_hash`.

Attempt IDs, run IDs, timestamps, durations, temporary paths, and artifact
directories are expected to vary and are not part of this invariant.

For the current local repo environment:

```text
controls run --repeats 2
  oracle repeat 1 and 2
    same status tuple
    same final_diff_hash
  bad.noop repeat 1 and 2
    same status tuple
    same final_diff_hash
  bad.public_only repeat 1 and 2
    same status tuple
    same final_diff_hash
```

## Why This Matters

Repeated control calibration only builds trust if repeated attempts are stable.
If the same deterministic control produces drifting statuses or diffs, the
harness may be leaking state across attempts or depending on nondeterministic
execution.

## Current Enforcement

`agentenv controls run` prepares a fresh attempt workspace for every repeat and
records each attempt result independently.

Current test evidence:

```text
tests/sandbox/test_invariants.py::test_repeated_control_runs_produce_stable_statuses_and_final_diff_hashes
```

## Current Limitation

This is a local file-layout invariant, not a security sandbox. It does not yet
prove process isolation, network isolation, filesystem mount restrictions, or
container hardening.
