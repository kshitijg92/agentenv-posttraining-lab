# Week 3 Learnings

## Main Mental Model

Week 3 was about measurement trust.

By the end of Week 2, the lab could run evals and replay them. Week 3 asked a
different question:

```text
Can I trust the harness enough to build more tasks and later training data on
top of it?
```

The answer is not a single pass/fail number. Trust comes from several layers:

```text
status taxonomy
scorer audit cases
repeated control calibration
local sandbox invariants
Docker smoke
explicit limitations
```

## Scorer Audit

The scorer audit is harness calibration, not a model eval.

It runs known patches through the normal attempt path and checks whether the
actual status tuple matches the expected status tuple:

```text
attempt_status
public_status
hidden_status
```

Current evidence:

```text
experiments/harness_audit/scorer_audit/
```

The current audit has 11 cases and all match:

```text
correct_oracle
wrong_noop
public_only_fix
public_test_fail
patch_changes_tests
hidden_validator_path_reference
leakage_canary_reference
malformed_patch_syntax
nonexistent_source_patch
public_check_timeout
hidden_check_timeout
```

The useful lesson is that statuses should be evidence-backed. For example,
`INVALID_SHORTCUT` is only used when the raw patch modifies public tests, and
`HIDDEN_VALIDATOR_ACCESS_ATTEMPT` is only used when the raw patch references
hidden-test assets or the leakage canary.

## Control Calibration

`eval run` records outcomes. `controls run` checks whether known controls behave
as expected.

Current command:

```bash
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/control_calibration
```

Current evidence:

```text
experiments/runs/control_calibration/
```

The current task pack produced:

```text
oracle: 3/3 attempt_status: PASS; public_status: PASS; hidden_status: PASS
bad.noop: 3/3 attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL
bad.public_only: 3/3 attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL
```

This is important because one oracle pass is weak evidence. Repeated known-good
and known-bad controls are stronger calibration evidence.

## Sandbox Invariants

The local sandbox invariants are about file-layout and artifact boundaries. They
are not a production security claim.

Current doc:

```text
docs/sandbox_invariants_v0.md
```

Current focused tests:

```text
tests/sandbox/test_invariants.py
```

The invariants now cover:

```text
hidden validators are not present in the prepared workspace
control patches are not present in the prepared workspace
each attempt starts from a fresh copy of workspace_seed
the leakage canary is absent from workspace files and all attempt artifacts
task.yaml contents are absent from workspace files and all attempt artifacts
deterministic control repeats have stable statuses and final_diff_hash
```

The key taste lesson: if an invariant is about "any artifact", the test should
scan every generated file under the artifact directory, not a hardcoded list.
Otherwise adding a new artifact can create a leak without the test noticing.

## Docker Smoke

Docker smoke is now present, but deliberately narrow.

Current command:

```bash
uv run agentenv sandbox smoke --config configs/sandbox/docker_none.yaml --out experiments/sandbox/docker_smoke
```

Current evidence:

```text
experiments/sandbox/docker_smoke/
```

The smoke check verifies:

```text
Docker can run the configured image
--network none is applied
a network probe fails under --network none
```

The current result passed:

```text
startup: returncode 0
network_probe: returncode 1 under --network none
```

This should not be described as secure sandboxing. It is an environment smoke
check.

## Debuggability

Week 3 also improved failure debuggability.

Unexpected exceptions inside the attempt path now produce:

```text
attempt_status: ORCHESTRATOR_ERROR
error_class
error.txt with exception message and traceback
trace.jsonl reference to error.txt
```

This matters because harness failures should be distinguishable from task
solution failures.

## What I Trust More Now

I trust more that:

```text
known-good controls pass
known-bad controls fail for expected reasons
public-test tampering is rejected before execution
hidden-validator probing is rejected before execution
public, hidden, and timeout failures are classified separately
private task assets are absent from prepared workspaces
private task content is absent from generated attempt artifacts
repeated deterministic controls are stable
Docker network-none smoke behaves as expected
```

## What I Still Should Not Overclaim

I should not claim:

```text
the scorer is generally reliable across many task families
the lab measures model capability yet
Docker is a secure hostile-code sandbox
the leakage detectors catch obfuscation or runtime probing
the audit artifacts are fully content-addressed or replayable
post-training quality improved
```

Current evidence is for one small Python repo-patch task pack and one local
Docker smoke path.

## Remaining Limitations

Important limitations:

```text
scorer-audit artifacts are regenerable but not fully replayable
patch-apply timeout is unit-tested but not represented by a real scorer-audit data case
hidden-validator access detection is explicit-string based
manifest override support is intentionally narrow
Docker smoke does not mount and run task workspaces yet
no resource limits beyond command timeouts are enforced
```

## Week 3 Takeaway

Eval harness trust is built by triangulation.

No single artifact proves the harness is trustworthy. The confidence comes from
the agreement between:

```text
expected-vs-actual scorer audit cases
repeated controls
workspace and artifact invariants
trace/debug artifacts
written limitations
```

This is the right foundation before adding more tasks, richer agents, rewards,
or post-training data.
