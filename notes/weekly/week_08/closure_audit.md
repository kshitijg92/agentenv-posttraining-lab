# Week 8 Closure Audit

## Sources

This audit checks the current repo against:

- `notes/weekly/week_08/plan.md`
- `references/agentic_evaluation_12_week_execution_manual.md`
- `experiments/reports/reward_hack_audit_week_08_v1.md`
- `experiments/runs/reward_hack_audit_week_08_v1/manifest.json`

## Verdict

Week 8 is closed.

The reward-hack audit now measures obvious reward/metric exploits separately
from task success and training eligibility. The suite covers all eight target
exploit classes from the manual with valid controls, machine-readable audit
artifacts, and a human-readable report.

This is not a reward-robustness claim. The correct claim is narrower:

```text
obvious reward-hack cases are measured separately from task success, the
implemented mechanisms are neutralized in the deterministic suite, and known
measurement holes are documented before Week 9 training-data work.
```

## Fresh Evidence

Canonical Week 8 reward-hack audit:

```bash
uv run agentenv rewards audit \
  --cases data/reward_hack_cases \
  --out experiments/runs/reward_hack_audit_week_08_v1 \
  --report-out experiments/reports/reward_hack_audit_week_08_v1.md \
  --overwrite
```

Observed:

```text
records: 16
passed: 16
failed: 0
private-content exposures: 0/16
exploit mechanisms detected: 16/16
exploit mechanisms neutralized: 16/16
training allowed: 0/16
task success allowed: 1/16
valid controls succeeded: 16/16
```

Artifact manifest:

```text
artifact_type: reward_hack_audit
artifact_schema_version: reward_hack_audit_artifact_v1
runtime_version: reward_hack_audit_runtime_v1
case_root: data/reward_hack_cases
record_count: 16
pass_count: 16
fail_count: 0
results_jsonl_hash: xxh64:c1a4b98a7fa073a7
```

Report:

```text
experiments/reports/reward_hack_audit_week_08_v1.md
```

Machine-readable results:

```text
experiments/runs/reward_hack_audit_week_08_v1/reward_hack_audit_results.jsonl
```

## Coverage

Implemented reward-hack classes:

```text
hidden_validator_probe_attempt
no_op_patch
public_test_only_pass
public_check_tampering
fake_success_output
tool_output_spoofing
format_only_compliance
state_corruption
timeout_or_retry_exploit
```

Authored cases:

```text
fake_success_output_correct_patch_agent_workspace_update
fake_success_output_hidden_fail_agent_workspace_update
format_only_compliance_submitted_patch_text_probe_attempt
hidden_validator_path_agent_tool_call_probe_attempt
hidden_validator_path_submitted_patch_text_probe_attempt
hidden_validator_timeout_submitted_patch_text_probe_attempt
leakage_canary_agent_tool_call_probe_attempt
leakage_canary_submitted_patch_text_probe_attempt
no_op_patch_submitted_patch_text_probe_attempt
public_check_tampering_submitted_patch_text_probe_attempt
public_check_timeout_submitted_patch_text_probe_attempt
public_test_only_pass_submitted_patch_text_probe_attempt
state_corruption_fake_attempt_agent_workspace_update
state_corruption_fake_manifest_agent_workspace_update
tool_output_spoofing_real_tools_plus_spoof_agent_workspace_update
tool_output_spoofing_spoof_only_agent_workspace_update
```

Evidence sources:

```text
agent_task_audit_case: 8
scorer_audit_case: 8
```

Valid-control reuse is explicit in the report:

```text
happy_path: 8 agent-backed cases
correct_oracle: 8 scorer-backed cases
```

This reuse is acceptable for the Week 8 fixture suite, but it weakens any claim
that each exploit has a highly specific paired positive example.

## Manual Criteria

The Week 8 manual required at least five reward-hack cases and targeted eight
exploit modes. The current suite exceeds the minimum and covers the target
exploit classes.

The manual required valid controls. Every authored reward-hack case has a valid
control, and the audit requires the valid control to pass on the same task
manifest.

The manual required reward-hack pass rate to be separate from task success. The
report separates:

```text
reward-hack audit pass
exploit mechanism detected
exploit mechanism neutralized
private-content exposure
task success allowed
training allowed
valid-control task success
```

The manual required known holes to be documented. The main preserved failure
note is:

```text
notes/failures/reward_hack_001.md
```

## Adapted Artifacts

The manual suggested:

```text
tests/fixtures/reward_hack_cases/
configs/eval/week08_reward_hack.yaml
data/task_packs/reward_hack_dev/
```

The implementation intentionally uses repo-native artifact locations:

```text
data/reward_hack_cases/
src/agentenv/rewards/
experiments/runs/reward_hack_audit_week_08_v1/
experiments/reports/reward_hack_audit_week_08_v1.md
```

We did not create a separate reward-hack task pack or eval config. The
fixture-level reward audit was a better fit for Week 8 because it directly
tests scorer/agent harness evidence, control pairing, leakage scans, and
training eligibility without requiring live model behavior.

## Baseline Gate

The real-model baseline was not rerun after the reward-hack suite was built.
The current baseline evidence remains:

```text
experiments/runs/qwen_model_eval_suite_sampling_4096
experiments/reports/eval_matrices/qwen_model_eval_suite_sampling_4096.md
notes/weekly/week_08/local_qwen_dev_run_analysis.md
```

Observed model-policy result:

```text
attempts: 3
final pass rate: 0/3
prompt-loop completed: 2/3
nested scorer run: 2/3
public pass: 2/3
hidden pass: 0/3
public-pass/hidden-fail: 2
max-turn failures: 1
invalid tool calls: 2
```

This is enough to answer the Week 8 gate conservatively:

- The task suite is stable enough for deterministic trace/export/filtering
  plumbing, because controls remain calibrated and reward-hack fixtures are
  measurable.
- The real-model pass rate is not informative for improvement claims; it is
  saturated at 0/3.
- Failures are mostly model-quality and agent-loop failures, not scorer
  infrastructure failures.
- Public-pass/hidden-fail remains the easiest reward component to misuse.
- Week 9 can proceed only as default trace-filtering/SFT plumbing, not as a
  model-improvement or reward-robustness claim.

## Remaining Limitations

These are limitations, not Week 8 blockers:

- Reward-hack cases are deterministic and hand-authored.
- No heldout-private reward-hack task pack exists.
- No full reward-hack eval config was created.
- Valid controls are reused heavily.
- The suite does not prove sandbox security.
- Hidden-validator leakage detection is intentionally limited to canaries and
  boundary markers, not validator-body similarity.
- `format_only_compliance` uses a narrow Python AST/docstring/comment check,
  not a general semantic no-op detector.
- `timeout_or_retry_exploit` only covers authored `actual_timeout` cases.
- Positive SFT remains empty; Week 9 should treat this as plumbing work unless
  new eligible positive trajectories are generated.

## Closure Decision

Week 8 should be treated as closed.

Proceed to Week 9 default trace-filtering/SFT plumbing with these constraints:

- do not train on reward-hack traces as positive examples;
- do not treat public-pass/hidden-fail as task success;
- keep reward-hack detection separate from trusted scorer task success;
- carry forward the known-hole note as a training-data gate;
- avoid model-improvement claims until the baseline pass rate becomes
  informative.
