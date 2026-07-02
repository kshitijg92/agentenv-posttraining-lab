# Construct Validity v0

## Purpose

This document states what the current `repo_patch_python_v0` eval can and
cannot measure.

Construct validity asks:

```text
Does this eval actually measure the capability we claim it measures?
```

For this lab, the answer must stay narrow. The task pack is a calibrated local
learning artifact, not a public benchmark or broad model-quality claim.

## Measured Construct

`repo_patch_python_v0` currently measures a compound capability:

```text
small localized Python repair under a strict JSON-action tool interface
```

More concretely, it measures whether a tool-using coding agent can:

- read a small prepared Python repository through the allowed tools;
- understand a focused behavioral repair request;
- edit one to two local files, usually across a few functions;
- use public checks as diagnostic feedback without treating them as the score;
- produce a candidate patch through the agent loop;
- pass hidden behavioral validators.

The strict tool-interface part is part of the measured construct today. A model
that cannot reliably emit exactly one valid JSON action per turn may fail this
eval even if it has useful coding ability in a different interface.

## Current Task Scope

The current task pack contains:

```text
practice:
  toy_python_fix_001

dev:
  repair_jsonl_deduper
  preserve_cli_error_codes
  repair_config_precedence
```

The tasks are deterministic local Python repo-patch tasks. They cover small
behavioral repairs such as JSONL validation, CLI exit-code behavior, and config
precedence/type validation.

They do not cover broad software engineering.

## Non-Claims

Results on this pack do not claim:

- broad coding-agent capability;
- general Python programming ability;
- large-repository navigation;
- multi-file architecture design;
- long-horizon planning;
- production debugging;
- UI, frontend, database, async, or distributed-systems work;
- secure sandboxing against a hostile agent;
- public benchmark comparability;
- model improvement from post-training.

Passing this eval means passing this narrow local task family under this
harness and interface.

## Primary Validity Risks

### Hidden Validator Leakage

If an agent can read hidden validators or hidden assets, the eval no longer
measures repair ability. It may measure whether the agent can inspect and
target the grader.

This is the highest-risk construct failure. A leaked hidden validator can turn
private behavioral scoring into visible test fitting.

Mitigations:

- hidden validators live outside the prepared agent workspace;
- task manifests record hidden validator paths separately from public checks;
- task validation checks hidden-validator path boundaries;
- leakage canaries exist in task metadata;
- reports and artifacts should not expose hidden validator contents to the
  model-facing path.

Invalidation condition:

```text
If hidden validator contents are agent-visible during an attempt, that attempt
must not be counted as evidence for coding ability.
```

### Weak Hidden Validators Or Public-Test Overlap

If hidden validators are too close to public tests, the eval may measure public
test fitting rather than robust repair.

Public checks are meant to be diagnostic. Hidden validators are the actual
measurement instrument.

Mitigations:

- every task has an oracle patch that must pass hidden validators;
- every task has a no-op bad control that must fail hidden validators;
- every task has a public-only bad control that must pass public checks but fail
  hidden validators;
- task reports separate public status from hidden status and final
  `AttemptStatus`.

Invalidation condition:

```text
If a public-only bad control passes hidden validation, the task is not
calibrated and should be excluded until fixed.
```

## Secondary Confounds

### Strict Tool Protocol

The v0 agent loop requires exactly one JSON action per model turn:

```json
{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/foo.py"}}
{"action": "final_answer", "text": "done"}
```

This makes the eval easier to audit, but it also means failure can reflect
protocol noncompliance rather than pure coding inability.

The DeepSeek R1 Distill Qwen local probe exposed this confound: the model could
reach the endpoint and emit a valid first tool call, but reasoning/prose
artifacts after tool results broke the strict action parser.

Reports should treat this as:

```text
model-interface failure, not necessarily coding-skill failure
```

### Small And Local Task Distribution

The current task distribution is intentionally small. It is useful for building
the lab loop and validating measurement discipline, not for estimating broad
model capability.

The heldout-private split is currently empty, so results should not be described
as heldout generalization.

### Public Checks As Feedback

Public checks are visible to the agent and can guide repair. This is intended,
but it means public pass rate is not task success.

A patch succeeds only when:

```text
attempt_status: PASS
public_status: PASS
hidden_status: PASS
```

### Artifact Drift And Flakiness

If deterministic controls produce different artifacts across repeats, then a
single score may hide unstable behavior.

Mitigations:

- repeated scorer controls compare normalized artifacts;
- repeated agent controls compare normalized agent artifact trees;
- flake detection treats one drifted repeat as a failure;
- human reports summarize flake status;
- JSON manifests store per-file drift evidence.

## Required Evidence Before Trusting Results

Before using results from this task pack as eval evidence, check:

- split membership is valid and locked;
- task input hashes are recorded for selected tasks;
- hidden validator paths do not leak into agent-visible workspaces;
- oracle controls pass;
- known-bad controls fail for the expected reason;
- public-only controls pass public checks but fail hidden validators;
- repeated controls are stable after normalization;
- trace and artifact manifests are present;
- reports separate scorer, agent, task, model, and infrastructure failures.

## What Would Invalidate The Eval

The current eval should not be trusted if any of these are true:

- hidden validators or canaries become visible to the agent;
- a known-bad control passes hidden validation;
- oracle controls fail;
- task hashes drift without being recorded in the eval manifest;
- a task appears in multiple splits or no split;
- repeated deterministic controls drift without explanation;
- public checks fully specify the hidden behavior;
- failures are collapsed into a single score without distinguishing model,
  protocol, scorer, task, sandbox, and infrastructure causes.

## Relationship To Trajectory And Reward Work

Trajectory export will later turn eval artifacts into rows containing task
metadata, prompt/task views, model actions, tool results, candidate patches,
scorer outcomes, and provenance.

Those exported rows are not automatically training data.

They become candidate reward, filtering, or training data only after construct
validity checks, split checks, hash checks, leakage checks, and flake checks say
the evidence is safe to reuse.

The purpose of this construct-validity document is to prevent future trajectory
or reward work from treating narrow, potentially confounded eval evidence as a
broader model-capability result.

## Version

The current construct-validity statement is:

```text
construct_validity_v0
```

Changing the task family, hidden-scoring semantics, model interface, or claim
scope should update this document and version.
