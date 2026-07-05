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
manifest_path
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
eval_suite_id
eval_run_id
eval_attempt_id
task_id
policy_id
attempt_index
agent_attempt_id
scorer_attempt_id
replay_run_id
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
eval_suite_json
manifest_json
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
`scorer_attempt_orchestrator_v0`, but that is producer/procedure provenance,
not the semantic scoring contract. The trajectory source provenance section
records `scoring_contract`, while the reward section records only
reward-component versioning and reward-signal hashes.

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
directly from `manifest.json`, attempt records, agent task artifacts, task
hash reports, and split lock evidence.

## Trajectory Review Workflow Ergonomics

The v0 review workflow intentionally keeps review as a separate artifact:

```text
TrajectoryExport -> review-init -> human edits reviews.jsonl -> review-validate
```

This preserves the provenance boundary, but the manual edit step is clunky.
`review-init` creates complete pending rows with nullable review fields:

```text
review_status = not_reviewed
review_id = null
reviewer_id = null
review_decision = null
```

To mark a row reviewed, the reviewer currently has to edit several JSONL fields
by hand. This is acceptable for the first audit path, but it is not a good
long-term review interface.

Later improvement options:

- a small CLI/script to mark one or more trajectories reviewed;
- a generated spreadsheet-style review file that round-trips into validated
  review JSONL;
- a simple local review app that reads the trajectory export and writes
  review records.

Do not solve this before the review artifact and validator are stable. The
important v0 boundary is that manual review does not mutate trajectory records,
and `review-validate` catches row deletion, duplication, unknown trajectory IDs,
identity drift, and incomplete reviewed rows before any training-candidate
export consumes the review artifact.

## Training Candidate Schema Boundary

The first training-candidate step is only a record schema, not an exporter.

`TrainingCandidateRecord` should be a joined eligibility surface over existing
artifacts, not a copy of those artifacts:

```text
TrajectoryExport + validated TrajectoryReview -> TrainingCandidateRecord
```

The row carries stable identity and review summary:

```text
trajectory_id
eval_attempt_id
task_id
policy_id
review_status
review_id
reviewer_id
review_decision
final_eligibility
```

It does not embed the full `TrajectoryRecord` or `TrajectoryReviewRecord`.
Future export manifests should pin the source trajectory/review artifacts by
path and hash, and rows should join by `trajectory_id`.

Final eligibility remains multi-path:

```text
analysis_allowed
positive_sft_allowed
negative_example_allowed
preference_data_allowed
```

Each path has a separate reason because a trajectory can be allowed for one
downstream use and blocked for another. Convenience properties such as
`is_trainable`, `is_analysis_only`, and `is_not_trainable` are derived in code,
not persisted as fields.

Review is a strict gate:

```text
any training path allowed -> review_status=reviewed and review_decision=accepted
```

Accepted review is necessary but not sufficient for trainability. The underlying
trajectory eligibility, split, leakage, orchestration, and reward-component
rules still decide which paths are allowed.

## Training Candidate Builder

The first builder is in-memory only:

```text
build_training_candidate_records(trajectory_export_dir, review_dir)
  -> tuple[TrainingCandidateRecord, ...]
```

It takes artifact directories, not raw JSONL paths. The builder first runs
`validate_trajectory_review_artifact(...)`, so it only joins review rows after
the review artifact has passed the whole-artifact one-to-one validation.

Join key:

```text
trajectory_id
```

Reason precedence:

1. If review is not accepted, all training paths are blocked regardless of the
   trajectory's mechanical eligibility.
2. If review is accepted but the trajectory policy is not an agent-model policy,
   all training paths remain blocked and the record stays analysis-only.
3. If review is accepted and the trajectory policy is an agent-model policy,
   final path booleans mirror the trajectory's mechanical eligibility.

This keeps human review as a strict gate without letting it override split,
leakage, orchestration, reward, status, or policy-origin rules. A reviewer can
block a candidate, but cannot make an otherwise ineligible trajectory trainable.

Control policies are still useful in trajectory exports, review artifacts, and
training-candidate exports because they support harness analysis and calibration.
They are not model-generated behavior, so even accepted control trajectories
must remain analysis-only. Training paths require a policy whose eval policy
type is the shared `AGENT_MODEL_POLICY_TYPE` constant from the eval schema.

This step deliberately does not write `manifest.json` or
`training_candidates.jsonl`; that artifact boundary comes next.

## Training Candidate Export Artifact

The training-candidate export persists the in-memory candidate join:

```text
TrainingCandidateExport
  manifest.json
  training_candidates.jsonl
```

The manifest pins both upstream artifacts, not only the review artifact:

```text
source_trajectory_export_dir
source_trajectory_export_manifest_hash
source_trajectories_jsonl_hash

source_review_dir
source_review_manifest_hash
source_reviews_jsonl_hash
```

It also records all three row schema versions at the join boundary:

```text
trajectory_record_schema_version
trajectory_review_schema_version
training_candidate_record_schema_version
```

Summary counts are stored in the manifest:

```text
analysis_allowed_count
positive_sft_allowed_count
negative_example_allowed_count
preference_data_allowed_count
trainable_count
analysis_only_count
not_trainable_count
```

The loader verifies the candidate JSONL hash, record count, and summary counts.
This makes the export auditable without rereading the upstream trajectory and
review artifacts for every summary check, while still preserving provenance back
to those source artifacts.

The export remains a candidate/index layer. It is not an SFT dataset or a
preference dataset.

## Message-Level Leakage Scan

Before designing the SFT dataset row, add a security primitive for the exact
payload the dataset exporter will emit:

```text
scan_messages_for_leakage(messages, task_manifest)
scan_texts_for_leakage(texts, task_manifest)
```

The trajectory builder already scans agent-visible artifacts, including
`prompt_loop_result.json`, but SFT export is a new trust boundary. It should
validate the exact model-visible messages that would be written to the training
dataset, rather than only trusting an upstream artifact scan.

The message scanner serializes each `Message` object and scans content,
metadata, names, and tool-call ids with the same canary/private-marker rules as
file scanning. Match refs use synthetic message labels such as:

```text
message:0:system
message:1:user
message:2:assistant
message:3:tool
```

The result shape stays compatible with `LeakageScanResult`; for message/text
scans, `scanned_files` contains these synthetic refs. This preserves one leakage
result contract while allowing the next exporter to gate on in-memory payloads.
