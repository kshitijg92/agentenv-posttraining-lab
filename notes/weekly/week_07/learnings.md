# Week 7 Learnings

## 2026-07-03

### Why Week 7 Exists

Week 7 is the bridge from eval measurement to post-training data discipline.

The repo already has a trusted scoring loop:

```text
task manifest + seed workspace -> policy attempt -> public checks ->
hidden scorer -> attempt artifacts -> replay/report
```

That is enough to measure attempts, but not enough to safely create training
data. Before any SFT, preference data, or filtering experiment, we need an
auditable record that says:

- where the attempt came from;
- what policy produced it;
- whether it was actually scored;
- whether it succeeded;
- what evidence supports that outcome;
- whether hidden/private information leaked;
- what downstream data uses are allowed.

The main reason for this week is to prevent a common post-training failure mode:
treating "we have traces" as equivalent to "we have trainable examples."

### Trajectory Boundary

One `TrajectoryRecord` should represent one eval attempt:

```text
one task x one policy x one attempt/repeat
```

This is the smallest useful end-to-end unit because it keeps the causal chain
intact:

```text
policy behavior -> candidate patch or failure -> public checks ->
hidden scorer result -> artifacts
```

Prompt-loop turns are too small because they do not carry task outcome.
Aggregates are too large because they hide failure modes.

The important separation is:

```text
exportable != scored != task_success != trainable
```

An attempt can be exportable for analysis even if it cannot be scored. A scored
attempt can fail. A successful attempt can still be disallowed for training if
it came from the wrong split, leaked hidden content, or failed review.

### Statuses vs Reward Components

Statuses describe what happened inside the harness lifecycle.

Examples:

```text
AgentTaskRunStatus
PromptLoopStatus
AttemptStatus
public_status
hidden_status
```

They answer:

```text
Where did execution end?
Did the prompt loop complete?
Did a scorer attempt run?
Did public checks pass?
Did hidden validators pass?
```

Reward components are evaluative signals derived from statuses and other
artifacts.

Examples:

```text
public_validator_success
hidden_validator_success
model_output_format_valid
model_tool_usage_valid
orchestration_failure
reward_hack_flag
```

They answer:

```text
Is this trajectory good, bad, risky, or unusable for a downstream data use?
```

Many v0 reward components are simple derivations from statuses, but keeping them
separate matters because later signals may come from patch analysis, manual
review, shortcut detection, tool-use analysis, or reward-hack audits.

The mental model:

```text
statuses = execution facts
reward_components = data-quality and reward signals
training_eligibility = downstream-use decision
```

### Public-Only Hidden-Fail

A public-only hidden-fail trajectory means:

```text
public_status = PASS
hidden_status = FAIL
task_success = false
```

This is a key pattern in the lab because public checks are intentionally
diagnostic only. Passing public tests does not mean the task was solved.

These failures are valuable, but not as positive imitation examples. They can be
used for:

- analysis of weak public tests;
- reward-hack detection;
- future negative examples;
- future preference pairs where this trajectory is the rejected side.

They should not be included as positive SFT targets by default, because that
would teach the model to imitate shortcut behavior.

### SFT Use

SFT means supervised fine-tuning: train the model to imitate selected target
outputs or trajectories.

For this repo, a future positive SFT example would likely be built from:

```text
task instruction + tool context -> successful assistant/tool-call trajectory
```

The model does not learn directly from fields like `hidden_success=true`.
Those fields are metadata used by the data pipeline to decide whether the
trajectory should be included.

For positive SFT, the filter should be conservative:

```text
hidden success
public success
valid format
valid tool use
no orchestration failure
no leakage
train-eligible split
not rejected by review
```

The self-deception trap is to treat any completed or public-passing trajectory
as a good training target.

### Preference Data

Preference data is different from SFT.

SFT says:

```text
imitate this good trajectory
```

Preference data says:

```text
for this prompt/task context, prefer trajectory A over trajectory B
```

A future preference pair might be:

```text
chosen: hidden-pass no-shortcut trajectory
rejected: public-pass hidden-fail shortcut trajectory
basis: successful_vs_public_only_shortcut
```

This could later support DPO or reward-model-style training, but Week 7 does not
implement those methods. Week 7 only preserves enough metadata to tell whether a
trajectory might be usable as a chosen or rejected side of a future pair.

### Training Eligibility

Training eligibility is not one boolean.

Different data uses have different rules, so the schema tracks:

```text
analysis_allowed
positive_sft_allowed
negative_example_allowed
preference_data_allowed
```

A failed trajectory can be useful for analysis or preference rejection while
still being forbidden for positive SFT.

Heldout-private and public-calibration examples must never become positive SFT
data. Environment failures and leakage cases must also be blocked from positive
training paths.

### Leakage Discipline

Raw canaries should not be copied into trajectory records.

Store:

```text
canary_hash
canary_leaked
hidden_validators_visible_to_model
leakage_check_version
```

The reason is simple: processed trajectory files are likely to feed later data
pipelines. They should not duplicate hidden validator content or private leakage
canaries.

### What The Schema Protects

The initial schema is not just bookkeeping. It protects against several bad
claims and bad data decisions:

- claiming prompt-loop completion as task success;
- claiming public-test success as task success;
- mixing scorer failure and orchestration failure;
- training on heldout or calibration data;
- training on leaked trajectories;
- treating every exported trajectory as positive SFT data;
- collapsing useful failure distinctions into one scalar reward.

The schema is intentionally conservative because later exporter and filtering
code will depend on these fields.
