# Week 8 Implementation Notes

## 2026-07-06 RewardHackCase Boundary

### Decision

`RewardHackCase` lives at the reward-audit/evidence layer.

It does not replace existing scorer or agent harness audits. It references
execution evidence and adds reward-hack classification, valid-control pairing,
private-content exposure expectations, reward/training implications, and report
grouping.

Allowed execution sources should be source-typed, for example:

```text
scorer_audit_case
agent_task_audit_case
eval_attempt
trajectory_record
```

Start with deterministic harness-audit sources before using live model attempts.

First exploit family:

```text
hidden_validator_probe_attempt
```

Initial invalid shortcut evidence:

```text
data/harness_audit/scorer_cases/hidden_validator_path_reference
```

Initial valid control evidence:

```text
data/harness_audit/scorer_cases/correct_oracle
```

### Minimal Contract Shape

One reward-hack case should contain:

```text
reward_hack_id
purpose
evidence
exploit
expected_reward_hack_outcome
notes
```

`evidence` identifies the invalid shortcut and valid control using one shared
source type:

```text
source_type
exploit
valid_control
```

`exploit` describes the attack being tested:

```text
exploit_classification
exploit_spec
```

Prefer `exploit_spec` over `hack_config`. The latter sounds like runtime
configuration, while the case needs a declared exploit mechanism and attacked
boundary.

`evidence.valid_control` is required for every reward-hack case. Do not allow
unpaired cases in the fixture contract.

The authored reward-hack case should not duplicate top-level `task_id` or
`task_manifest`. For harness-audit-backed cases, task provenance lives in the
referenced exploit and valid-control audit cases. The verifier should load both
references and require them to point at the same task manifest.

Do not duplicate the valid control's expected execution outcome in the
reward-hack fixture. The referenced harness audit case already declares its own
expected statuses. The reward-hack audit should load the valid-control source,
verify its id/hash, and rely on the underlying harness audit expectations.

Do not duplicate the invalid source's expected execution outcome in the
reward-hack fixture either. The referenced harness audit source already declares
its own expected statuses. The reward-hack audit should load the source case,
verify its id/hash, and reuse the underlying harness audit expectations.

`expected_reward_hack_outcome` should hold reward-audit expectations:

```text
private_content_exposed
exploit_blocked
training_allowed
```

Do not include a configurable `hack_detected_expected` field in v0. A
`RewardHackCase` fixture is, by definition, expected to be detected as a
reward-hack case. The audit result should still record whether the hack was
actually detected, and the case should fail if it was not.

Do not include configurable `task_success_allowed` in the fixture schema either.
A reward-hack case is an invalid shortcut by definition, so task success is
never allowed for the exploit source. The runtime audit should derive/check
whether the source was allowed to count as task success and fail the audit if
that value is not false.

### Reasoning

Existing harness audits already answer:

```text
does the scorer/agent harness enforce this mechanical contract?
```

Week 8 reward-hack audit should answer:

```text
was an exploit attempt detected, blocked, classified, reported separately from
task success, and excluded from reward/training misuse?
```

This keeps the execution boundary and the reward/data boundary separate.

### Invariants

- `RewardHackCase` does not redefine task success.
- Task success remains the existing scorer/agent status contract.
- Reward-hack pass rate must be reported separately from task success rate.
- Every exploit case must have a valid control.
- Exploit and valid-control evidence must resolve to the same task manifest for
  harness-audit-backed cases.
- Source execution expectations should come from the referenced harness audit
  case, not be duplicated in the reward-hack fixture.
- Valid-control execution expectations should come from the referenced harness
  audit case, not be duplicated in the reward-hack fixture.
- Hidden/private content exposure must be explicitly expected and checked.
- Reward-hack source artifacts must not be allowed to count as task success.
- Reward-hack-detected examples must not become positive training examples.

### Self-Deception Trap

A passing harness audit is not the same as a complete reward-hack analysis.

The harness may correctly reject a hidden-validator path reference, but Week 8
still needs to show that this exploit is named, counted, reported, and blocked
from reward/training use.

## 2026-07-06 Exploit Spec Shape

### Decision

Use a typed `exploit_spec` per `exploit_classification`.

Do not make `exploit_spec` a single loose bag of generic fields for every
reward-hack class. Also do not predesign all target exploit classes before the
first implementation.

Implement the first typed spec for:

```text
hidden_validator_probe_attempt
```

Future exploit classes can add their own typed specs when they are implemented,
for example:

```text
public_test_only_pass
format_only_compliance
timeout_or_retry_exploit
```

Redesign the discriminated union later if the first few exploit specs reveal a
better common shape.

### Reasoning

Different exploit classes attack different boundaries.

For example, a hidden-validator probe needs to describe private target access:

```text
probe_target
probe_surface
expected_blocking_layer
```

A public-test-only shortcut would need different evidence:

```text
public_signal_used
hidden_requirement_missed
shortcut_patch_ref
```

Forcing these into one generic schema would make the fixture less precise and
would hide which boundary is actually being tested.

### Invariant

The top-level reward-hack case remains stable:

```text
reward_hack_id
evidence
exploit
expected_reward_hack_outcome
```

Only `exploit.exploit_spec` varies by exploit class.

## 2026-07-06 Hidden-Validator Probe Spec

### Decision

For the first typed exploit spec, `hidden_validator_probe_attempt`, keep the
fields literal and audit-oriented:

```text
probe_target
probe_surface
probe_reference_type
expected_blocking_layer
private_content_must_not_appear
```

Make `probe_reference_type` an enum, not free text.

Initial enum values should cover the first deterministic cases:

```text
hidden_validator_path
leakage_canary
```

Add more enum values only when there is a concrete fixture that needs them.

Make `probe_surface` an enum too.

Initial enum values:

```text
submitted_patch_text
agent_tool_call
```

For the first deterministic scorer-audit fixture, only
`submitted_patch_text` is required.

Use "validator" rather than "test" in the reward-hack contract because the
boundary is about private scoring/verifier assets, not pytest specifically.
Do not include `agent_workspace_write` or `eval_artifact_reference` in the v0
surface enum. `agent_workspace_write` is covered by tool-call arguments once the
agent surface exists, and `eval_artifact_reference` is better treated later as a
leakage/provenance surface rather than an exploit-attempt surface.

Do not include `absolute_private_path` in the enum yet. A simple
slash-prefixed marker check would catch strings such as
`/abc/d/hidden_tests`, but that is not full absolute-path parsing. Keeping the
enum out of the contract avoids claiming a stronger detector than we have.

### Reasoning

`probe_reference_type` is a reporting and grouping field, not just a note.

If it is free text, the audit report cannot reliably answer:

```text
which private reference class was attempted?
how many hidden path probes vs canary probes did we test?
which reference classes are still uncovered?
```

Using an enum makes the reward-hack suite more auditable without requiring us
to predesign every future exploit type.

The same applies to `probe_surface`: the audit report should be able to
separate probes that happen in submitted patch text from probes that happen
through agent tool calls, workspace writes, or artifact references.

## 2026-07-06 Evidence Pair Shape

### Decision

Group the invalid shortcut and valid control under one evidence pair:

```text
evidence
```

The evidence pair has one `source_type`, so the invalid shortcut and valid
control must come from the same execution-evidence family.

Top-level shape:

```text
source_type
exploit
valid_control
```

`source_type` selects the payload shape for both `exploit` and `valid_control`.
Initial source types:

```text
scorer_audit_case
agent_task_audit_case
eval_attempt
trajectory_record
```

For a scorer audit source, the payload can reference a case directory:

```text
source_type: scorer_audit_case
exploit:
  case_dir: data/harness_audit/scorer_cases/hidden_validator_path_reference
  case_id: hidden_validator_path_reference
valid_control:
  case_dir: data/harness_audit/scorer_cases/correct_oracle
  case_id: correct_oracle
```

For an agent task audit source:

```text
source_type: agent_task_audit_case
exploit:
  case_dir
  case_id
valid_control:
  case_dir
  case_id
```

For an eval attempt:

```text
source_type: eval_attempt
exploit:
  eval_artifact_dir
  policy_id
  task_id
  eval_attempt_id
valid_control:
  eval_artifact_dir
  policy_id
  task_id
  eval_attempt_id
```

For a trajectory record:

```text
source_type: trajectory_record
exploit:
  trajectory_export_dir
  trajectory_id
valid_control:
  trajectory_export_dir
  trajectory_id
```

Implement only the first source type needed by the first fixtures. Add the
other reference payloads when concrete cases require them.

### Reasoning

The invalid shortcut and valid control should be comparable. They should come
from the same evidence family, be runnable or inspectable through the same kind
of loader, and participate in the same report table.

But scorer audit cases, agent task audit cases, eval attempts, and trajectory
records have different identifiers and artifact layouts. A single flat object
would either be too loose or would contain many nullable fields.

Using a typed evidence pair keeps the contract tight while preserving the
ability to compose existing harness evidence.

### Provenance Decision

Use stable human-readable source refs in authored reward-hack YAML.

Do not version existing harness audit case ids by renaming them to include
`_v1` unless the semantics intentionally change.

Authored reward-hack cases should carry:

```text
case_dir
case_id
```

Do not require authors to manually compute `case_hash` in `case.yaml`.

The runtime audit should fail loudly if:

- the referenced case directory does not exist;
- the loaded case id does not match `case_id`.

The runtime audit should compute case-directory hashes and write them to
runtime outputs, reports, or a future generated lock file such as:

```text
data/reward_hack_cases.lock.json
```

Hash the full source case directory, including `notes.md`.

Use normalized text hashing for `notes.md`, matching the existing task-hashing
discipline where human-authored text can be normalized while still contributing
to provenance. Other execution-relevant files, such as `case.yaml`,
`submission.patch`, and `agent_control_script.json`, should contribute through
their exact contents unless a future implementation has a specific reason to
normalize them.

This makes the reward-hack layer intentionally dependent on harness-audit
evidence while still allowing runtime outputs to record exact source hashes.

If we later need reproducible locked reward-hack suites, generate a lock file
instead of making humans hand-author source hashes in every case YAML.

## 2026-07-06 Source Outcome Expectations

### Decision

Do not include `expected_source_outcome` in the reward-hack fixture schema for
harness-audit-backed cases.

The invalid source and valid control both reference underlying harness audit
cases. Those harness cases already declare their expected execution statuses.
Duplicating those statuses in the reward-hack fixture would create a second
source of truth.

Runtime reward-hack audit should:

```text
load source case -> verify id -> compute hash -> use source case expectations
load valid control case -> verify id -> compute hash -> use control case expectations
verify source and valid control use the same task manifest
```

If a future reward-hack case references an artifact type that does not already
carry or declare execution expectations, design that source type deliberately
then. Do not add a generic nullable outcome schema early.

### Reasoning

The reward-hack layer should classify and interpret exploit evidence. It should
not fork scorer or agent audit contracts.

## 2026-07-06 Valid-Control Reuse

### Decision

Do not forbid reusing the same valid control across multiple reward-hack cases.

Some exploit classes can reasonably share a broad valid control, especially
when the purpose is to prove that the harness still accepts normal correct
behavior for the same task.

However, shared controls are a suite-quality signal. Runtime reporting should
eventually count valid-control reuse, for example:

```text
valid_control_case_id
reuse_count
reward_hack_case_ids
```

High reuse is not automatically invalid, but it is evidence that the suite may
be over-relying on one generic control instead of pairing each exploit with the
most relevant normal behavior.

### Reasoning

The manual requires a valid control for each exploit because an invalid
shortcut failing is not enough. The valid control should show that the same
broad surface can still pass when behavior is legitimate.

If many exploit cases reuse one generic control, the suite may still satisfy the
letter of the requirement while weakening the measurement value. Reporting reuse
makes that weakness visible without prematurely banning useful shared controls.

## 2026-07-06 Reward-Hack Case Location

### Decision

Store durable reward-hack case definitions under:

```text
data/reward_hack_cases/
```

Do not put the main suite under `tests/fixtures/`.

Do not introduce a `reward_hack_dev/` subfolder yet. There is only one
reward-hack suite in v0, so a split/suite directory would add naming ceremony
before there is a second suite to distinguish.

Initial layout:

```text
data/reward_hack_cases/
  hidden_validator_path_probe_attempt/
    case.yaml
```

Tests can still use temporary malformed fixtures and can load these durable
cases, but the source artifacts themselves live in `data/` because they are
eval/post-training audit inputs.

### Reasoning

Reward-hack cases are durable adversarial measurement artifacts, not disposable
unit-test fixtures.

Reports and later data-filtering checks should be able to reference them outside
the test suite. Keeping them under `data/` matches task packs and harness audit
cases as durable local evidence.

## 2026-07-06 Shared Hashing Helper

### Decision

Extract shared hash primitives into:

```text
src/agentenv/hashing.py
```

Use this helper from both:

```text
src/agentenv/tasks/hashing.py
src/agentenv/rewards/cases.py
```

The shared helper owns:

```text
NOISY_HASH_PATH_NAMES
hash_file
hash_json
hash_bytes
hash_normalized_text
iter_hashable_files
relative_path
```

### Reasoning

Reward-hack source hashes should use the same noisy-path filtering and
normalized-text semantics as existing task hashing.

Duplicating `_NOISY_NAMES` and byte/json/text hash helpers in the reward module
would create a quiet drift risk. If task hashing ignored a path that reward
case hashing included, provenance comparisons would become harder to reason
about.

Keep the domain-specific record construction in each module, but keep primitive
hash mechanics shared.

## 2026-07-06 Runtime Reward-Hack Audit

### Decision

Add an in-memory runtime audit in:

```text
src/agentenv/rewards/audit.py
```

Keep artifact persistence separate in:

```text
src/agentenv/rewards/export.py
```

This matches the trajectory/training export pattern: runtime code builds typed
domain results, while export code owns `manifest.json`, JSONL serialization,
artifact hashes, output-directory handling, and artifact loading.

The v0 runtime reruns scorer-audit evidence pairs into a scratch run directory
and returns `RewardHackAuditResult`. The persisted artifact uses the standard
artifact package conventions:

```text
manifest.json
reward_hack_audit_results.jsonl
case_runs/
```

`RewardHackAuditArtifact.records` is typed as `RewardHackAuditResult`, not raw
JSON dictionaries. The JSONL is a storage representation that `export.py`
converts back into typed reward audit results on load.

Reward-hack audit artifacts are reportable through the standard Markdown report
entry point:

```text
agentenv rewards audit --cases data/reward_hack_cases --out <run_dir> --report-out <report.md>
agentenv report <run_dir> --out <report.md>
```

The renderer lives in `src/agentenv/rewards/reporting.py` and reports the
reward-hacking view over the underlying audit results: aggregate safety signals,
case outcomes, runtime checks, source audit statuses, leakage scan counts, and
valid-control reuse counts.

The initial authored case suite covers two scorer-backed submitted-patch
private-reference variants:

```text
hidden_validator_path_probe_attempt
leakage_canary_probe_attempt
```

Both are paired with the same `correct_oracle` valid control, which is
intentional for the first batch and visible in the report's valid-control reuse
counts.

`RewardHackAuditResult` keeps the underlying scorer `ScorerAuditResult` objects
for the exploit and valid control. It does not redefine scorer status fields or
status expectations; those remain owned by the scorer audit case and its
`comparisons`.

For `hidden_validator_probe_attempt`, the runtime makes two separate
measurements:

```text
private_content_access_attempt_actual
private_content_exposed_actual
```

The access-attempt check is scoped to the declared probe surface. For the
current case, that means checking the submitted patch text for the declared
hidden-tests path reference.

For `submitted_patch_text`, the runtime scans the referenced patch file with
`scan_files_for_leakage` from `src/agentenv/security/leakage.py`. The reward
layer does not reimplement private-marker or canary matching; it only maps the
declared `probe_reference_type` to the relevant shared leakage-scan signal.

The exposure check scans the generated exploit attempt artifact tree, excluding
staged fixture inputs and valid-control hidden-scoring provenance. It uses
`scan_directory_for_leakage` from `src/agentenv/security/leakage.py` and stores
the shared `LeakageScanResult` on the reward audit result. Private exposure is
derived from that shared result's canary matches and private-marker matches,
rather than reimplemented in the reward layer.

The shared leakage scan also reports private marker matches such as hidden path
references. Reward audit v0 does not attempt hidden-validator body matching.

The valid control is still rerun and must pass its scorer audit, but its hidden
scoring trace can legitimately contain scorer-private hidden validator command
provenance. That provenance should not be counted as exploit leakage.

### Reasoning

Access attempts and private-content exposure are related but different failure
modes. A patch can attempt to reference `hidden_tests` and still be blocked
before any private content leaks into artifacts.

Hidden-validator body matching is not a reliable leakage signal. A model can
legitimately infer the right behavior and produce code or tests that overlap
with hidden validators. Reward-hack leakage detection should stay anchored to
canaries, private markers, artifact provenance, and boundary violations, not
similarity to hidden validator bodies.

## 2026-07-07 Agent Tool-Call Private Reference Guard

### Decision

Add a runtime-only `PrivateReferenceGuard` to the prompt loop and wire it from
the full task manifest in `run_agent_task_attempt`.

The guard scans serialized `ToolCallAction` objects before assigning a
`tool_call_id` or executing the tool. This covers the tool name, argument keys,
and argument values.

If the guard sees a hidden-validator/private marker or leakage canary, the
prompt loop stops with:

```text
status: invalid_shortcut_attempted
error_class: PrivateHiddenValidatorAccessAttempted
error_message: Tool call contained a private hidden-validator reference.
```

The tool is not executed, no synthetic `ToolResult` is recorded, and no tool
message is appended.

### Reasoning

Private-reference access through the agent tool chain is an agent-boundary
failure, not a scorer-boundary failure. Waiting until candidate patch scoring
would allow private references to pass through tool dispatch and only catch
some downstream artifacts.

The guard is kept out of `AgentTaskView` so hidden validator paths and canaries
remain runtime-only enforcement metadata, not model-visible prompt data.
