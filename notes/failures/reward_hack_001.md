# reward_hack_001: Public-Visible Success Is The Easiest False Reward Signal

## Summary

The most important Week 8 reward-hack failure mode is treating public-visible
success, compliant output shape, or model-authored success artifacts as task
success.

This is the failure future training-data work must not ignore:

```text
public or apparent success != trusted task success
```

## Exploit Mechanism

Several Week 8 cases attack the same weak measurement habit from different
directions:

```text
public_test_only_pass
no_op_patch
format_only_compliance
fake_success_output
tool_output_spoofing
state_corruption
timeout_or_retry_exploit
```

The common shortcut is to produce a signal that looks useful to a shallow
selector:

```text
public_status=PASS
non-empty patch
valid-looking patch format
fake score.json PASS
fake tool_results.json SUCCESS
fake manifest.json or attempt.json
timeout/retry ambiguity
```

None of these should become positive training evidence unless trusted scoring
and reward-hack review allow it.

## Affected Reward Component Or Metric

Affected signals:

```text
public_status
prompt_loop_status
candidate_patch_non_empty
workspace-authored JSON files
artifact-looking provenance files
timeout/retry status
```

Protected authority:

```text
task_success = trusted scorer / nested AttemptResult PASS
training_allowed = separate reward-hack/data-use decision
```

## Invalid Shortcut Behavior

The invalid shortcut generally has this shape:

```text
model emits something that looks successful
public or shallow checks appear favorable
hidden/trusted scorer does not establish task success
```

Concrete examples from the current suite:

```text
public_test_only_pass_submitted_patch_text_probe_attempt
no_op_patch_submitted_patch_text_probe_attempt
format_only_compliance_submitted_patch_text_probe_attempt
fake_success_output_hidden_fail_agent_workspace_update
tool_output_spoofing_spoof_only_agent_workspace_update
state_corruption_fake_attempt_agent_workspace_update
public_check_timeout_submitted_patch_text_probe_attempt
```

## Valid Control Behavior

Every current reward-hack case has a valid control.

Scorer-backed cases use:

```text
data/harness_audit/scorer_cases/correct_oracle
```

Agent-backed cases use:

```text
data/harness_audit/agent_task_cases/happy_path
```

The Week 8 report verifies:

```text
valid controls succeeded: 16/16
```

## Current Mitigation

Current mitigation is measurement and data-use separation:

```text
trusted task success remains scorer-owned
reward-hack mechanisms are detected and reported separately
training_allowed is always false for authored reward-hack cases
private-content exposure is scanned separately from access attempts
```

Canonical report:

```text
experiments/reports/reward_hack_audit_week_08_v1.md
```

Observed:

```text
record_count: 16
pass_count: 16
exploit mechanisms detected: 16/16
exploit mechanisms neutralized: 16/16
training allowed: 0/16
task success allowed: 1/16
private-content exposures: 0/16
```

The one task-success-allowed exploit is intentional:

```text
fake_success_output_correct_patch_agent_workspace_update
```

It proves that a correct patch can remain task-correct while the spoofed
success artifact still makes the trajectory non-trainable.

## Remaining Hole

The suite is hand-authored and deterministic. It does not prove reward
robustness, sandbox security, or broad resistance to novel reward hacks.

Specific weak spots:

- valid controls are reused heavily;
- hidden-validator leakage detection does not match validator bodies;
- format-only detection is a narrow Python AST/docstring/comment check;
- timeout detection covers authored actual-timeout fixtures only;
- no heldout-private reward-hack suite exists;
- no full reward-hack eval task pack was created.

## Week 9 Gate

This hole does not block Week 9 default trace-filtering/SFT plumbing, but it
does constrain the claim.

Week 9 may proceed only if:

- public-pass/hidden-fail trajectories are excluded from positive SFT;
- reward-hack-detected trajectories are not positive training examples;
- fake success/provenance/tool files are treated as exploit evidence, not
  authoritative records;
- timeout outcomes remain non-success outcomes;
- training exports preserve review/reward-hack gates.

Week 9 must not claim model improvement or reward robustness unless new,
trusted positive trajectories and stronger reward-hack coverage are added.
