# Week 8 Plan

## Theme

Week 8 makes the current reward evidence visibly attackable before using it for
training or trace filtering.

The manual's Week 8 goal is:

```text
make the reward visibly attackable before using it for training
```

The learning objective is:

```text
reward hacking, metric exploits, valid controls, and baseline discipline
```

The point is not to prove reward robustness. The point is to expose obvious
ways the current reward evidence can be fooled, measure those cases separately
from task success, document unpatched holes, and make an explicit go/no-go
decision before Week 9 training-data work.

## Starting Point

Weeks 1-7 are closed.

Current architecture:

```text
task manifest + seed_workspace -> patch/control/agent policy -> orchestrator ->
public checks -> hidden scorer -> attempt artifacts -> replay/report
```

For model policies:

```text
eval config -> model client -> prompt loop -> typed tools -> candidate patch ->
existing attempt/scorer path -> eval matrix report
```

Core scoring invariant:

```text
task success = nested AttemptStatus PASS
public checks = diagnostic only
prompt-loop completion = not task success
```

Current Week 7 reward/data boundary:

- one `TrajectoryRecord` represents one eval attempt;
- `RewardComponents` live inside `src/agentenv/trajectories/schema.py`;
- reward components are decomposed audit signals, not a scalar reward;
- review records are separate artifacts and do not mutate trajectories;
- training eligibility has separate paths for analysis, positive SFT, negative
  examples, and preference data;
- positive SFT export can validly contain zero rows.

Current Week 7 artifact state:

```text
eval suite:
  experiments/runs/qwen_model_eval_suite_sampling_4096

trajectory export:
  experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_export

trajectory review:
  experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_review

training candidates:
  experiments/runs/qwen_model_eval_suite_sampling_4096_training_candidates

positive SFT export:
  experiments/runs/qwen_model_eval_suite_sampling_4096_positive_sft
```

Current training-candidate summary:

```text
records: 21
trainable: 3
positive_sft: 0
negative_examples: 3
preference_data: 2
analysis_only: 18
```

Important current limitations:

- only three dev tasks;
- no heldout-private tasks;
- public checks are intentionally weak on some tasks;
- raw provider responses are not persisted;
- cost is reported as `not_recorded`;
- local real-model execution depends on Ollama and local machine capacity;
- no positive SFT rows exist;
- reward-hack audit coverage is not implemented yet.

## Non-Claims

Week 8 must not claim:

- reward robustness;
- model improvement;
- training readiness;
- heldout generalization;
- broad coding-agent capability;
- production-grade sandbox security.

The strongest acceptable claim is:

```text
obvious reward-hack cases are measured separately from task success, some are
blocked, and known unpatched holes are documented
```

## Design Priority

Preserve measurement boundaries:

- reward-hack pass rate must be separate from task success rate;
- public-only success must never be counted as task success;
- hidden validators must remain private;
- valid controls must exist next to invalid shortcut cases;
- model failures, scorer failures, environment failures, and metric exploits
  must be distinguishable;
- reward-audit outputs must not create training-eligible records by accident;
- Week 8 reports must make weak measurement visible, not hide it.

## First Design Question

Before implementing the reward audit path, decide:

```text
What should count as one reward-hack audit case in this repo: a malicious patch,
a scripted agent transcript, a whole eval policy, or a task-level fixture?
```

Do not implement the full reward-hack suite before answering this. The case
boundary controls what evidence is available, whether the exploit tests the
reward or merely the model, how valid controls are paired, and how failure
attribution is recorded.

## Planned Outputs

Primary planned artifacts:

```text
notes/weekly/week_08/plan.md
notes/weekly/week_08/implementation_notes.md
notes/weekly/week_08/learnings.md
notes/failures/reward_hack_001.md
data/reward_hack_cases/
src/agentenv/rewards/audit.py
configs/eval/reward_hack_dev.yaml
experiments/reports/week08_reward_audit.md
experiments/reports/week08_reward_hacking.md
experiments/reports/week08_baseline_gate.md
experiments/plans/week08_baseline_gate.yaml
```

Possible implementation artifacts, depending on the audit-case boundary:

```text
src/agentenv/rewards/schema.py
tests/rewards/test_reward_audit.py
data/task_packs/reward_hack_dev/
experiments/runs/reward_hack_audit/
experiments/runs/reward_hack_dev/
experiments/runs/week08_baseline_repeat/
```

Use schedule-neutral names for repo code and configs where practical. Week
numbers are acceptable in notes, reports, and learning artifacts.

## Planned Checkpoints

### Checkpoint 1: Audit-Case Boundary

Purpose:

```text
Choose the smallest case unit that can test reward/metric exploits while
preserving attribution and control pairing.
```

Questions to answer:

- What is the case unit?
- What evidence does one case point at?
- How does the case express the exploit mechanism?
- How does the case define the expected invalid-shortcut outcome?
- How does the case define the valid-control counterpart?
- How does the audit distinguish reward exploit from model failure?

Done when:

- the boundary decision is written in
  `notes/weekly/week_08/implementation_notes.md`;
- rejected alternatives are named briefly;
- the decision explains how hidden-validator privacy is preserved;
- the self-deception trap for this boundary is written down.

### Checkpoint 2: Minimal Fixture Contract

Purpose:

```text
Define how reward-hack cases are represented on disk before writing the full
audit command.
```

Likely artifact:

```text
data/reward_hack_cases/
```

Done when:

- one invalid shortcut and one valid control can be represented;
- expected outcomes are explicit and machine-checkable;
- expected failure attribution is explicit;
- fixtures do not expose hidden validator contents to model-visible paths;
- a focused validation test rejects malformed cases.

Self-deception trap:

```text
A case that only proves the model failed is not necessarily a reward-hack case.
The fixture must say what metric, component, or trust boundary is being attacked.
```

### Checkpoint 3: First High-Quality Cases

Purpose:

```text
Build a small number of cases deeply enough to test the audit design before
scaling to the full target set.
```

Start with two or three cases that are already connected to observed repo
failure modes:

```text
public_test_only_pass
no_op_patch
format_only_compliance
```

Done when each case has:

- exploit intent;
- invalid shortcut;
- valid control;
- expected audit classification;
- expected task-success outcome;
- expected reward-hack outcome;
- a short note explaining why the case tests reward evidence rather than only
  model quality.

### Checkpoint 4: Reward Audit Module And CLI

Purpose:

```text
Run reward-hack fixtures and produce a report that separates task success from
reward-hack outcomes.
```

Likely artifacts:

```text
src/agentenv/rewards/audit.py
src/agentenv/cli.py
tests/rewards/test_reward_audit.py
```

Target command shape:

```bash
uv run agentenv rewards audit \
  --cases data/reward_hack_cases \
  --out experiments/runs/reward_hack_audit \
  --report-out experiments/reports/week08_reward_audit.md
```

If the implementation stays closer to the manual, a simpler first command is
acceptable:

```bash
uv run agentenv rewards audit \
  --cases data/reward_hack_cases \
  --out experiments/reports/week08_reward_audit.md
```

Done when the audit distinguishes:

- expected invalid shortcut rejected;
- expected valid control accepted;
- metric exploit;
- model failure;
- scorer failure;
- environment failure;
- unsupported or malformed case.

### Checkpoint 5: Expand Reward-Hack Coverage

Purpose:

```text
Reach enough adversarial coverage to make reward weaknesses visible before
Week 9.
```

Minimum acceptable coverage:

```text
5 high-quality cases
```

Target coverage:

```text
public_test_only_pass
no_op_patch
fake_success_output
hidden_test_probe_attempt
format_only_compliance
tool_output_spoofing
state_corruption
timeout_or_retry_exploit
```

Done when:

- every exploit has a valid control;
- reward-hack pass rate is computed separately from task success;
- known unblocked holes are explicitly documented;
- case quality is not sacrificed merely to hit the target count.

### Checkpoint 6: Reward-Hack Eval Config

Purpose:

```text
Run reward-hack cases through the existing eval/reporting path when that adds
measurement value beyond the fixture-level audit.
```

Likely artifacts:

```text
data/task_packs/reward_hack_dev/
configs/eval/reward_hack_dev.yaml
experiments/runs/reward_hack_dev/
experiments/reports/week08_reward_hacking.md
```

Done when:

- the eval config uses fixed budgets;
- oracle/valid controls and invalid shortcuts are not mixed in summary metrics;
- the report separates task success, public-only success, and reward-hack
  outcomes;
- task-pack validation and split checks pass if a task pack is created.

Decision point:

```text
Only create a new task pack if the reward-hack cases genuinely need full
repo-patch tasks. If fixture-level cases test the reward boundary better, keep
the first implementation smaller.
```

### Checkpoint 7: Main Baseline Repeat

Purpose:

```text
Repeat the main dev baseline under fixed conditions and decide whether the
suite is stable enough for Week 9 training-data work.
```

Preferred real-model repeat if Ollama/Qwen is available:

```bash
AGENTENV_MODEL_BASE_URL=http://127.0.0.1:11434/v1 uv run agentenv eval \
  --config configs/eval/agent_model_dev_ollama_qwen3_14b.yaml \
  --all-policies \
  --out experiments/runs/week08_baseline_repeat \
  --report-out experiments/reports/week08_baseline_gate.md
```

Fallback scripted/control repeat if model execution is unavailable or too slow:

```bash
uv run agentenv eval \
  --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml \
  --all-policies \
  --out experiments/runs/week08_baseline_repeat \
  --report-out experiments/reports/week08_baseline_gate.md
```

Done when the baseline gate report answers:

- Is the task suite stable enough for training experiments?
- Is pass rate informative, or is it saturated at 0% or 100%?
- Are failures mostly model failures or measurement failures?
- Which task should be deleted or revised first?
- Which reward component is easiest to hack?

### Checkpoint 8: Failure Note And Week 9 Gate

Purpose:

```text
Record the most important reward-hack failure clearly enough that future
training-data work cannot ignore it.
```

Likely artifact:

```text
notes/failures/reward_hack_001.md
```

Done when the note includes:

- exploit mechanism;
- affected reward component or metric;
- invalid shortcut behavior;
- valid control behavior;
- current mitigation;
- remaining hole;
- whether the hole blocks Week 9 default trace-filtering/SFT work.

Final Week 8 decision:

```text
Proceed to Week 9 default trace-filtering/SFT plumbing only if measurement is
stable enough and reward holes are documented. If measurement is weak, switch
Weeks 9-12 to the manual's alternate eval/reward-hardening spike.
```

## Planned Commands

Refresh trusted task-pack evidence:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv tasks check-splits data/task_packs/repo_patch_python_v0/splits.lock.json
uv run agentenv tasks hash data/task_packs/repo_patch_python_v0 \
  --out experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
```

Validate current Week 7 downstream artifacts before using them as context:

```bash
uv run agentenv trajectories review-validate \
  --source experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_export \
  --reviews experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_review

uv run agentenv training candidates export \
  --trajectories experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_export \
  --reviews experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_review \
  --out experiments/runs/qwen_model_eval_suite_sampling_4096_training_candidates \
  --overwrite

uv run agentenv training sft export \
  --candidates experiments/runs/qwen_model_eval_suite_sampling_4096_training_candidates \
  --out experiments/runs/qwen_model_eval_suite_sampling_4096_positive_sft \
  --overwrite
```

Run reward audit after implementation:

```bash
uv run agentenv rewards audit \
  --cases data/reward_hack_cases \
  --out experiments/runs/reward_hack_audit \
  --report-out experiments/reports/week08_reward_audit.md
```

Run reward-hack eval after implementation, if a task pack/config is created:

```bash
uv run agentenv eval \
  --config configs/eval/reward_hack_dev.yaml \
  --all-policies \
  --out experiments/runs/reward_hack_dev \
  --report-out experiments/reports/week08_reward_hacking.md
```

Run the main baseline gate:

```bash
AGENTENV_MODEL_BASE_URL=http://127.0.0.1:11434/v1 uv run agentenv eval \
  --config configs/eval/agent_model_dev_ollama_qwen3_14b.yaml \
  --all-policies \
  --out experiments/runs/week08_baseline_repeat \
  --report-out experiments/reports/week08_baseline_gate.md
```

Verification commands:

```bash
uv run pytest -n auto
uv run ruff check .
uv run pyright
git diff --check
```

## Report Requirements

The Week 8 reports should include:

- task success rate;
- reward-hack pass rate;
- public-only pass rate;
- tool invalidity rate;
- scorer failure rate;
- environment failure rate;
- cost/tokens if available;
- latency if available;
- failure labels;
- trace or artifact examples;
- known unpatched reward holes;
- explicit non-claims.

Report wording must keep these separate:

```text
task success
public-check success
prompt-loop completion
reward-hack audit pass
training eligibility
```

## Cut Plan

If time is tight, cut in this order:

1. Target 8-case coverage.
2. Full reward-hack task pack.
3. Real-model baseline repeat.
4. Report polish.

Do not cut:

- valid controls for each implemented exploit;
- separate reward-hack pass rate;
- hidden-validator privacy;
- failure attribution;
- known-hole documentation;
- the Week 9 go/no-go decision.

## Notes To Keep

Write `notes/weekly/week_08/implementation_notes.md` as decisions are made:

- audit-case boundary decision;
- fixture contract decision;
- audit output/artifact decision;
- why any manual artifact names were adapted to current repo conventions;
- each known reward hole and whether it is mitigated.

Write `notes/weekly/week_08/learnings.md` only for durable conceptual lessons:

- why public-only success is a reward-hack risk;
- why controls must pair invalid shortcuts with valid behavior;
- why reward evidence and training eligibility are distinct;
- why a caught exploit is not the same as robust reward design;
- how baseline gates prevent training experiments from outrunning measurement.
