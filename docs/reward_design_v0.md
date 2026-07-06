# Reward Design v0

## Purpose

This document defines how v0 reward evidence should be interpreted for
trajectory export and review.

The v0 reward design is intentionally modest:

```text
RewardComponents are decomposed audit signals, not a scalar reward.
```

They help explain why a trajectory may be useful for analysis, positive SFT,
negative examples, or preference data. They do not prove reward validity, model
improvement, or training readiness.

## Scope

Reward evidence is stored in:

```text
TrajectoryRecord.reward_components
```

The full `TrajectoryRecord` is the audit envelope. It carries identity,
provenance, policy, statuses, artifacts, leakage evidence, reward components,
and training eligibility.

`RewardComponents` is narrower. It carries reward-relevant signals derived from
trajectory statuses and attempt artifacts:

```text
public_validator_success
hidden_validator_success
model_output_format_valid
model_tool_usage_valid
orchestration_failure
reward_hack_flag
```

It also carries reward derivation metadata:

```text
reward_version
reward_config_hash
reward_code_hash
```

The current scoring contract version is carried in
`TrajectoryRecord.source_provenance.scoring_contract`, not duplicated inside
`RewardComponents`.

## Component Semantics

`public_validator_success` records whether public checks passed when a scorer
attempt exists. Public success is diagnostic only. It is not task success.

`hidden_validator_success` records whether hidden validators passed when a
scorer attempt exists. Hidden success is the primary task-success signal, but it
is only meaningful if hidden validators remained private and the task/scorer
harness was calibrated.

`model_output_format_valid` records whether an agent trajectory complied with
the strict JSON-action interface well enough to avoid an invalid-output prompt
loop failure.

`model_tool_usage_valid` records whether the model's tool interaction completed
without a terminal tool-use error. A trajectory can have valid tool usage and
still fail the task.

`orchestration_failure` records whether the run ended in an orchestrator or
harness failure rather than a normal model/task outcome.

`reward_hack_flag` records explicit scorer statuses that indicate shortcut or
hidden-validator access behavior. In v0 this is a narrow flag, not a complete
reward-hacking detector.

`None` for a component means the signal was not applicable or could not be
observed for that trajectory. For example, scorer components are `None` for an
agent loop that never produced a candidate patch to score.

## Trust Conditions

Reward components are trusted only under explicit measurement assumptions.

For one trajectory, the reward evidence is trustworthy only if:

- the source trajectory export and referenced artifacts validate by hash;
- the task manifest and split provenance match the recorded source evidence;
- no canary leak was detected;
- hidden validators were not visible to the model;
- hidden validator contents were not copied into model-visible artifacts;
- the trajectory did not end in an orchestrator or harness failure;
- no reward-hack flag is set;
- the human review accepts the trajectory as not shortcutting, leaking, or
  otherwise invalid for its recorded outcome.

For a run or suite-level claim, the reward evidence additionally requires
harness trust:

- oracle controls pass;
- known-bad controls fail for the expected reason;
- public-only controls pass public checks but fail hidden validators;
- scorer and agent audit reports do not show harness instability;
- task hashes and split locks have not drifted;
- replay or repeat evidence does not show unexplained nondeterminism.

These suite-level checks are not the same as a row's reward components. They are
the evidence that the components can be believed.

## Untrusted Conditions

Reward evidence must be treated as untrusted if any of these are true:

- canary text leaks;
- hidden validators or hidden validator paths become model-visible;
- source artifact hashes drift;
- task manifests or split locks drift without being recorded;
- oracle controls fail;
- known-bad controls pass;
- audit reports show scorer, agent, replay, or control instability;
- a task instruction is ambiguous enough that hidden validators define new
  requirements instead of checking stated behavior;
- the trajectory ends in an orchestrator or harness failure;
- reward-hack behavior is detected or strongly suspected.

Untrusted reward evidence must block reward-dependent training paths. It can
still be useful for debugging the harness, but it should not be used as a
positive SFT example, negative example, or preference-data row.

## Relationship To Training Eligibility

Reward trust and training eligibility are related but different.

Reward trust asks:

```text
Can we believe the measured signals?
```

Training eligibility asks:

```text
Given trusted signals, review, split policy, and policy origin, what downstream
uses are allowed?
```

The invariant is:

```text
untrusted reward evidence -> no reward-dependent training use
trusted reward evidence -> maybe training eligible
```

Reward trust is necessary but not sufficient for training eligibility.

Examples:

- A public-pass, hidden-fail model trajectory can have trusted reward evidence
  as a failure signal. It is not positive SFT eligible, but may be useful later
  as a negative example or rejected side of a preference pair.
- A successful control-policy trajectory can have trusted reward evidence, but
  it is not model-generated behavior and should remain analysis-only.
- A successful model trajectory from `public_calibration` can have trusted
  reward evidence, but split policy still blocks positive training use.
- A leaked trajectory is not training-eligible even if its public and hidden
  statuses are `PASS`.

## Current Qwen Sampling Result

The current reviewed Qwen sampling artifact produced no positive SFT rows.

The three `local-qwen-dev` trajectories were reviewed and accepted for the
recorded outcomes, but none are positive-SFT eligible:

- `repair_jsonl_deduper` passed public checks and failed hidden validators;
- `preserve_cli_error_codes` exceeded the maximum turn limit and could not be
  graded;
- `repair_config_precedence` passed public checks and failed hidden validators.

This is a valid Week 7 outcome. It shows that the pipeline can preserve failure
evidence without turning failed or ungraded traces into positive imitation data.

## Current Limitations

The v0 reward design has important limits:

- no scalar reward is defined;
- no learned reward model is defined;
- reward components are mostly deterministic derivations from statuses;
- public checks are intentionally weak and diagnostic;
- `reward_hack_flag` only captures explicit known statuses;
- suite-level control and audit evidence is not embedded inside
  `RewardComponents`;
- the task set is small and dev-only;
- heldout-private generalization is not measured;
- positive SFT, negative example, and preference exports remain downstream data
  contracts, not reward validity claims.

## Non-Claims

This document does not claim:

- reward validity;
- model improvement;
- broad coding-agent capability;
- heldout generalization;
- production-grade sandbox security;
- that any exported trajectory is automatically trainable.

It defines when v0 reward components may be inspected and when they must be
treated as untrusted.
