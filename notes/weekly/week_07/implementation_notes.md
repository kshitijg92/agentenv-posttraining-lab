# Week 7 Implementation Notes

## 2026-07-03

### Shipped

Created the Week 7 plan:

```text
notes/weekly/week_07/plan.md
```

### Decision

Use one eval attempt as the `TrajectoryRecord` boundary.

One trajectory record represents:

```text
one task x one policy x one attempt/repeat, from policy execution through
nested scoring if scoring exists
```

This is the smallest end-to-end unit that preserves the causal chain from policy
behavior to scorer outcome.

### Reasoning

Attempt-level records preserve:

- task and split provenance;
- policy identity;
- prompt-loop/tool behavior when the policy is an agent;
- direct or nested scorer outcome;
- public-check and hidden-scorer separation;
- artifact references needed for replay and audit;
- training eligibility decisions without treating every exported record as
  trainable data.

Prompt-loop turns are too small because they do not carry scorer outcomes.
Task/policy aggregates are too large because they hide individual failure modes.
Direct scorer attempts and agent attempts should share the same outer trajectory
record shape, with agent-only fields nullable or absent when the policy is a
scorer-control policy.

### Status Contract

Reuse existing lifecycle status vocabulary:

```text
AgentTaskRunStatus
PromptLoopStatus
AttemptStatus
public_status
hidden_status
```

For agent/model policies, task success means:

```text
AgentTaskRunStatus == scored
PromptLoopStatus == completed
nested AttemptStatus == PASS
public_status == PASS
hidden_status == PASS
```

For scorer-control policies, task success means:

```text
direct AttemptStatus == PASS
public_status == PASS
hidden_status == PASS
```

Do not count `PromptLoopStatus == max_turns_exceeded` as task success under the
current contract. Today, max-turn agent runs are not scored because the runner
returns `agent_loop_failed` with no nested `AttemptResult`. Scoring partial
workspace state at max turns would be a separate runner contract change.

### Section-Level Schema Shape

Use small denormalized fields for invariants plus artifact references and hashes
for auditability.

Top-level sections should be:

```text
identity
source_provenance
policy
statuses
artifacts
reward_components
leakage
training_eligibility
review
```

Fields needed for safety gates should be denormalized into the trajectory.
Examples:

```text
task_id
split
policy_id
attempt_status
public_status
hidden_status
task_success
training_allowed
```

Fields needed for forensic audit can be artifact references with hashes.
Examples:

```text
eval_config_path
run_manifest_path
task_manifest_path
splits_lock_path
trace_jsonl
agent_task_run_json
prompt_loop_result_json
candidate_patch
nested_attempt_json
final_diff
error_txt
```

### Leakage Decision

Do not copy raw leakage canaries into trajectory records.

Store leakage evidence as checks and hashes instead:

```text
canary_hash
agent_visible_canary_detected
hidden_validator_refs_visible_to_agent
leakage_check_version
```

Raw canary text should remain in task-private assets. Processed trajectory files
are likely to feed later data pipelines, so they should not duplicate secrets or
hidden validator content.

### Self-Deception Trap

An exported trajectory is not necessarily model-viewable and not necessarily
trainable.

Separate:

```text
exportable
scored
task_success
training_allowed
training_use
```

Public-test-only hidden-fail trajectories are useful for analysis, reward audit,
preference rejection, or later negative/adversarial data. They are not positive
SFT examples.

### Next Small Step

Define the minimal required fields inside each top-level section, then implement
only the schema skeleton and validation tests before building the exporter.

### Field Contract Draft

Initial required sections:

```text
identity
source_provenance
policy
statuses
artifacts
reward_components
leakage
training_eligibility
review
```

`identity` should include stable identifiers such as:

```text
trajectory_id
run_id
task_id
policy_id
attempt_id
```

`source_provenance` should include denormalized safety-gate fields plus artifact
references and hashes:

```text
task_id
split
scoring_contract
task_manifest_path
task_manifest_hash
splits_lock_path
splits_lock_hash
eval_config_path
eval_config_hash
```

`policy` should identify the policy source:

```text
policy_id
policy_name
policy_spec
```

Decision: `policy_spec` should reuse `EvalPolicy` from `agentenv.evals.schema`
instead of redefining policy type literals in the trajectory schema. The
trajectory schema can add trajectory-specific identity fields, but it should not
fork the eval policy contract.

`statuses` should carry lifecycle facts from the existing harness:

```text
agent_task_run_status
prompt_loop_status
attempt_status
public_status
hidden_status
grade_state
task_success
```

Use:

```text
grade_state = scored_pass | scored_fail | cannot_grade
task_success = true | false
```

`artifacts` should point to source evidence rather than duplicating large data:

```text
eval_run_path
eval_matrix_path
run_manifest_json
agent_task_run_json
prompt_loop_result_json
candidate_patch
attempt_json
trace_jsonl
stdout
stderr
error_txt
final_diff
```

`leakage` should store leakage check results and hashes, not raw hidden content:

```text
canary_hash
canary_leaked
hidden_validators_visible_to_model
leakage_check_version
```

`reward_components` are machine-derived evaluative signals from statuses and
other artifacts, not lifecycle statuses themselves. Initial components:

```text
public_validator_success
hidden_validator_success
model_output_format_valid
model_tool_usage_valid
orchestration_failure
reward_hack_flag
```

Versioning decision:

```text
reward_version
reward_config_hash
reward_code_hash
```

`reward_version` is owned by the trajectory/reward schema, so it should be a
literal/default constant in code. `scoring_contract` is source/measurement
provenance, not a reward component, because it comes from the task-pack
manifest and defines the semantic task-success contract under which statuses and
reward signals are interpreted.

`review` is initially empty or `not_reviewed`, then filled after manual audit:

```text
review_status
review_id
reviewer_id
review_decision
review_notes_ref
```

`review_decision` is an enum, not free text:

```text
accepted
rejected
needs_followup
```

The review decision is intentionally coarse. It records whether the reviewed
trajectory record passed human audit, failed it, or needs more investigation.
Specific downstream uses remain in `training_eligibility`, and detailed reasons
belong in review notes.

`training_eligibility` should separate possible future uses:

```text
analysis_allowed
positive_sft_allowed
negative_example_allowed
preference_data_allowed
eligibility_reason
```

Decision: training eligibility is not a single boolean. Different downstream
uses have different safety rules. A trajectory can be valuable for analysis or
preference rejection while still being disallowed for positive SFT.

### Shipped

Added the first trajectory schema checkpoint:

```text
src/agentenv/trajectories/__init__.py
src/agentenv/trajectories/schema.py
tests/trajectories/test_schema.py
```

The schema encodes the v0 sections:

```text
identity
source_provenance
policy
statuses
artifacts
reward_components
leakage
training_eligibility
review
```

Validation rules implemented:

- `task_success=true` requires `grade_state=scored_pass`;
- `grade_state=cannot_grade` requires `task_success=false`;
- `grade_state=scored_pass` requires `AttemptStatus`, `public_status`, and
  `hidden_status` to all be `PASS`;
- `positive_sft_allowed=true` requires `task_success=true`;
- `positive_sft_allowed=true` is forbidden for `heldout_private` and
  `public_calibration`;
- `positive_sft_allowed=true` is forbidden when canary leakage or visible hidden
  validators are detected;
- leakage evidence stores `canary_hash` and rejects extra raw canary fields;
- `not_reviewed` records cannot include review details;
- `reviewed` records require review id, reviewer id, and review decision;
- identity task/policy ids must match source provenance and policy sections.

### Correction

The first schema draft duplicated eval policy type strings in a local
`PolicyType` alias. That was the wrong ownership boundary.

Updated the trajectory schema to reuse:

```text
agentenv.evals.schema.EvalPolicy
```

The trajectory record now stores:

```text
policy_id
policy_name
policy_spec: EvalPolicy
```

This keeps the eval config schema as the source of truth for policy shapes and
prevents trajectory export from drifting into a parallel policy taxonomy.

Second correction: the first schema draft used `grader_version`.

That was unclear. In this repo, the relevant measurement contract is:

```text
scoring_contract_v0
```

from:

```text
data/task_packs/repo_patch_python_v0/manifest.yaml
```

The patch-attempt artifact also records an `orchestrator_version`, currently
`attempt_v0`, but that is an artifact/runtime version, not the semantic scoring
contract. The trajectory source provenance section records `scoring_contract`,
while the reward section records only reward-component versioning and
reward-signal hashes.

Third correction: `scoring_contract` does not belong in `reward_components`.

It helps interpret reward components like `hidden_validator_success`, but it is
not itself a reward signal. It belongs in `source_provenance` with task/split
evidence. The reward section now owns:

```text
reward_version
reward_config_hash
reward_code_hash
public_validator_success
hidden_validator_success
model_output_format_valid
model_tool_usage_valid
orchestration_failure
reward_hack_flag
```

Use `orchestration_failure`, not `environment_failure`, for v0. The signal we
need here is whether the harness/orchestrator/scorer/export path failed in a way
that makes the reward signal unusable. If we later need to distinguish sandbox
or task-environment failures from orchestrator failures, add a separate field
with a narrower definition.

Fourth clarification: `leakage_check_version` should remain a provenance field
in the schema, but the constant should be owned by the future leakage-checker
implementation.

The trajectory schema defines what leakage evidence must be carried:

```text
canary_hash
canary_leaked
hidden_validators_visible_to_model
leakage_check_version
```

It should not define the checker algorithm version until that checker exists.
When implemented, the checker/exporter should provide something like:

```text
LEAKAGE_CHECK_VERSION = "leakage_check_v0"
```

from the module that actually performs the leakage scan.

### Ran

```bash
uv run pytest tests/trajectories/test_schema.py
uv run ruff check src/agentenv/trajectories tests/trajectories
uv run pyright src/agentenv/trajectories tests/trajectories
git diff --check
uv run ruff check .
uv run pyright
uv run pytest -n auto
```

### Result

```text
tests/trajectories/test_schema.py: 13 passed
ruff: passed
pyright: 0 errors
git diff --check: passed
full pytest: 380 passed
```

### Next Small Step

Inspect current eval-run artifact shapes and design the exporter input mapping:

```text
eval run artifacts -> TrajectoryRecord sections
```

Do not implement export yet until the mapping identifies which fields can be read
directly from `run_manifest.json`, attempt records, agent task artifacts, task
hash reports, and split lock evidence.
