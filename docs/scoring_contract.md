# Scoring Contract

## Purpose

This document defines what counts as success for one repo-patch task attempt and
what must be true before a task is trusted enough to include in a baseline
report.

It separates two related but different ideas:

```text
attempt success = one submitted patch passes the task
task calibration = controls show the harness and validators behave as expected
```

Both matter. A patch result is not trustworthy unless the task is calibrated,
but calibration is not itself a patch success.

## Attempt Success

The primary task outcome is the final `AttemptStatus`.

A submitted patch succeeds only when:

```text
attempt_status: PASS
public_status: PASS
hidden_status: PASS
```

In the current harness, `PASS` means:

- the patch applied cleanly,
- every public check passed,
- every hidden validator passed,
- the attempt completed without timeout or orchestrator error.

Any other final `AttemptStatus` is not task success.

## Public Checks

Public checks are diagnostic feedback. They are not the score.

Public checks should:

- catch very shallow failures,
- give the agent a small visible contract,
- remain intentionally incomplete,
- avoid revealing the full hidden behavior.

Passing public checks alone must not imply task success. A patch that passes
public checks but fails hidden validators is a failed attempt with:

```text
attempt_status: HIDDEN_TEST_FAIL
public_status: PASS
hidden_status: FAIL
```

## Hidden Validators

Hidden validators are the primary measurement instrument.

They should encode the behavior that the task is actually trying to measure,
including edge cases that are absent from public checks.

Hidden validators must be:

- deterministic,
- local,
- private to the evaluator side,
- absent from the prepared agent workspace,
- absent from agent-visible artifacts,
- specific enough to reject the public-only bad control.

Hidden validators should not compensate for an ambiguous task instruction. If
the intended behavior cannot be stated clearly, the task should be rewritten or
excluded.

## Control Calibration

Every task must include controls before it can be trusted in a baseline:

```text
controls/scorer_control_patches/oracle.patch
controls/scorer_control_patches/bad_noop.patch
controls/scorer_control_patches/bad_public_only.patch
controls/agent_control_scripts/happy_path.json
controls/agent_control_scripts/malformed_json.json
controls/agent_control_scripts/bad_tool_input_then_recovery.json
```

The scorer control patches calibrate the patch-attempt/scoring path. The agent
control scripts calibrate the model-agent loop before a candidate patch is
scored.

Expected outcomes:

```text
oracle:
  attempt_status: PASS
  public_status: PASS
  hidden_status: PASS

bad.noop:
  attempt_status: HIDDEN_TEST_FAIL
  public_status: PASS
  hidden_status: FAIL

bad.public_only:
  attempt_status: HIDDEN_TEST_FAIL
  public_status: PASS
  hidden_status: FAIL
```

If an oracle fails, the task is not calibrated.

If a known-bad control passes, the task is not calibrated.

If a known-bad control fails for an unexpected reason, the task needs review
before it can be counted. For example, a public-only control should fail hidden
validation, not fail to apply.

## Baseline Reporting Rules

Baseline reports must separate:

- public-check pass rate,
- hidden-validator pass rate,
- final `AttemptStatus` pass rate,
- oracle control pass rate,
- known-bad control pass rate,
- replay match rate,
- environment failures,
- scorer or orchestrator failures,
- task exclusions.

Do not report a policy pass rate without also reporting whether controls and
replay behaved as expected.

Do not mix oracle control performance with model or scripted-policy performance.
The oracle is a calibration control, not a baseline agent.

## Task Exclusion Rules

A task should be excluded or blocked from the baseline if:

- the oracle control does not pass,
- a known-bad control passes,
- hidden validators leak into the prepared workspace or artifacts,
- the instruction is ambiguous enough that hidden tests define new requirements,
- repeated deterministic controls are unstable,
- an orchestrator or scorer failure prevents a normal attempt outcome,
- the task needs external services, network access, wall-clock timing, or
  nondeterministic resources.

Every exclusion must be written down with the task id, command, observed result,
and reason.

## Versioning

The current scoring contract is:

```text
scoring_contract_v0
```

Changing the meaning of task success, adding new required controls, or changing
hidden-validator semantics should create a new scoring-contract version in
task-pack metadata and reports.

Adding more tasks under the same rules does not require a new scoring-contract
version.

## Non-Claims

This scoring contract does not claim:

- broad coding-agent capability,
- model improvement,
- secure sandboxing,
- public benchmark validity,
- general reliability outside the local repo-patch task family.

It defines the local evidence required before this project can treat a task
attempt as successful.
