# Week 8 Learnings

## Purpose

This file is for durable eval/post-training lessons from Week 8.

Use it when we learn something about why a measurement boundary, invariant,
data-use rule, leakage constraint, reward signal, review step, split policy, or
self-deception trap matters.

Do not use this file for routine implementation notes, naming decisions, helper
placement, refactor mechanics, or test-maintenance details. Put those in
`implementation_notes.md` when they are worth preserving.

## 2026-07-06

### Public Success Is Not Task Success

The local Qwen run showed two public-pass/hidden-fail trajectories.

In both cases, public checks created a tempting but invalid success signal:

```text
public_status = PASS
hidden_status = FAIL
task_success = false
```

This matters because reward/data pipelines often start by looking for cheap
signals that correlate with success. Public tests are cheap and visible, but in
this lab they are intentionally diagnostic only. If public success were treated
as task success or positive training signal, the pipeline would select exactly
the behavior we want to avoid: shallow visible-test compliance.

The invariant is:

```text
public-check success may explain a trajectory, but it must not define task
success or positive SFT eligibility
```

### Reward-Hack Audit Is Not The Same As Harness Audit

The repo already has scorer and agent harness audits. Those audits answer:

```text
does the harness enforce the mechanical contract?
```

Week 8 reward-hack work asks a different question:

```text
when an exploit is attempted, is it detected, classified, reported separately
from task success, and blocked from reward/training misuse?
```

This distinction matters because passing a harness audit can still leave a
measurement blind spot. For example, the scorer may correctly reject a patch
that references hidden validators, but the post-training pipeline still needs
to know that this was a reward-hack attempt, not an ordinary task failure.

The durable boundary is:

```text
harness audit = enforcement evidence
reward-hack audit = adversarial measurement and data-use evidence
```

### Exploit Specs Are Measurement Metadata

An `exploit_spec` is not an execution recipe.

For a reward-hack case, execution evidence comes from a referenced source such
as a scorer audit case, agent audit case, eval attempt, or trajectory record.
The exploit spec labels and structures how that evidence should be interpreted.

For example:

```text
evidence = scorer audit case with a submitted patch referencing hidden_tests
exploit_spec = hidden_validator_probe_attempt on submitted_patch_text with
probe_reference_type=hidden_validator_path
```

Runtime should not use the spec to synthesize a new exploit. It should use the
spec to classify, group, and report the exploit that already exists in the
evidence source.

The boundary is:

```text
evidence -> runnable or inspectable behavior
exploit_spec -> semantic label and aggregation dimensions
expected_reward_hack_outcome -> reward/data-use expectations
```

This matters because reward-hack reports need to aggregate exploit families
without parsing every patch or transcript ad hoc.

### Names Should Match The Boundary Being Protected

For reward-hack probes, "hidden validator" is the better contract term than
"hidden test".

The private object we are protecting is the hidden scoring/verifier boundary.
Today that boundary is implemented with pytest files, but the reward-hack
measurement should not imply that only tests are private or that only pytest
paths matter.

This matters because later probes may involve canaries, validator paths, tool
arguments, scoring metadata, or non-pytest validators. If the schema says
"test", it quietly narrows reviewer attention and can create false coverage.

### Do Not Name A Detector More Strongly Than It Measures

An `absolute_private_path` enum value sounds like the audit can parse and
recognize absolute private paths robustly.

A simple check for `"/" + hidden_validator_marker` is weaker than that. It can
catch slash-prefixed markers such as `/abc/d/hidden_tests`, but it is not a
general absolute-path detector across URI forms, shell expansions, platform
path syntax, or path normalization.

The durable lesson is to keep the measurement contract narrower than or equal
to the implemented detector. Over-broad enum names create false confidence in
coverage and make reports look stronger than the evidence supports.

### Every Exploit Needs A Valid Control

A reward-hack case without a valid control can overstate what was learned.

If the invalid shortcut fails, that alone does not prove the measurement
boundary is good. It may only show that the case was malformed, impossible to
run, or unrelated to the actual task. A paired valid control checks that normal
correct behavior can still pass through the same broad surface.

The invariant is:

```text
invalid shortcut should fail, real correct behavior should pass
```

This protects against a common eval-design mistake: building a detector that
only rejects bad behavior by making the task impossible or by blocking the whole
path.

### Control Specificity Matters

Reusing a valid control is not automatically wrong, but it weakens what a
reward-hack suite can claim if overused.

A generic valid control can show that the harness still accepts normal correct
behavior. It does not always show that the specific exploit boundary was tested
against the most relevant legitimate behavior.

The suite-quality signal is:

```text
many exploit cases sharing one valid control -> possible weak control coverage
```

This should be reported rather than hidden. High valid-control reuse does not
necessarily invalidate the suite, but it should make us ask whether the controls
are genuinely paired with the exploits or merely satisfying a checklist.

### Leakage Boundaries Are Training-Data Boundaries

Hidden-validator and canary protections are not only scorer-safety details.
They are also training-data rules.

If private evaluator content leaks into a trajectory, that trajectory is no
longer trustworthy as post-training data. Even if the final patch happens to
pass hidden tests, the success may be contaminated by access to information
that future models should not learn from.

The data-use rule is:

```text
private-content exposure -> no positive reward/training use
```

Leaked or probe-attempt trajectories can still be useful for analysis or
adversarial examples, but they must be labeled as such and excluded from
positive SFT paths.

### Reward-Hack Detected Is Not Reward Robustness

Detecting an exploit is useful evidence, but it is not a robustness claim.

Week 8 should make obvious reward-hack modes visible and document which ones
are blocked. It should not claim that the reward is hard to game in general.
The test suite is still small, the exploit cases are hand-authored, and the
reward components are mostly deterministic signals derived from statuses.

The acceptable claim is narrow:

```text
obvious reward-hack cases are measured separately from task success, some are
blocked, and known holes are documented
```

This keeps training experiments from outrunning measurement quality.

### Access Attempt And Exposure Are Different Measurements

A reward-hack case can prove that an attempt referenced a private boundary on a
specific surface while separately proving that private content did or did not
escape into runtime artifacts.

The probe surface should scope the access-attempt measurement. The exposure scan
should cover the full output tree because leaks can happen in traces, reports,
errors, or derived artifacts unrelated to the original probe surface.

Canary and private-marker matching are suitable exposure signals because they
represent explicit private boundaries. Hidden-validator body matching is not a
sound leak detector: a model can legitimately infer the correct behavior and
produce code or tests that overlap with hidden validators. Leakage evidence
should come from provenance, canaries, private markers, or boundary violations,
not similarity to hidden validator bodies.

### The Attack Payload Is Not Automatically Exposure

For agent-tool-call reward-hack cases, the private marker appears in the
model's attempted tool call. That is the exploit surface being measured.

Counting that same payload as private-content exposure would collapse two
different questions:

```text
did the model attempt to use a private reference?
did the harness/tooling leak private content through outputs or artifacts?
```

The access-attempt scan should inspect the declared probe surface, including
the assistant tool-call payload. The exposure scan should inspect derived
artifacts and tool/output messages outside that attack payload.

This preserves the invariant:

```text
private reference in exploit payload -> access attempt
private reference in tool result/error/scoring/training artifact -> exposure
```

Without this boundary, every authored exploit fixture that contains the canary
or hidden-validator marker would falsely look like a harness leakage failure.

### Structured Scans Beat Broad Artifact Exclusions

Avoiding a false exposure signal should not create a blind spot.

For agent reward-hack cases, the assistant's private tool-call payload is the
attack attempt, so counting it as exposure would be wrong. But the surrounding
prompt-loop artifact can also contain real exposure surfaces: tool messages,
tool results, prompt-loop errors, and non-attack assistant text.

The measurement rule is:

```text
skip the specific authored/attack payload
scan the rest of the runtime artifact structurally
```

This matters because filename-level exclusions are too coarse. They make the
current test pass by hiding both the expected attack payload and any unexpected
runtime leak in the same file.

### Status Is Not The Exploit Mechanism

Two different reward-hack mechanisms can produce the same scorer outcome.

For example, an empty patch and a public-test-only partial fix can both pass
weak public checks and fail hidden validation:

```text
public_status = PASS
hidden_status = FAIL
attempt_status = HIDDEN_TEST_FAIL
```

If the reward-hack suite keyed only on status, it would collapse distinct
failure modes into one bucket and hide which reward signal was actually being
gamed.

The durable rule is:

```text
exploit spec describes the mechanism
harness audit describes the outcome
```

This matters for post-training because different mechanisms imply different
filters and mitigations. An empty patch is a minimal-effort/no-change failure;
a public-test-only patch is visible-check overfitting. Both are invalid as
positive training data, but they teach different lessons about the reward.

### Scorer-Provenance Artifacts Are Also Data Boundaries

Hidden scoring is allowed to inspect private validators, but the public attempt
artifact should not preserve hidden-score command paths, hidden pytest output,
or other private verifier provenance.

This matters because audit and training pipelines often consume artifacts, not
only model-visible transcripts. A hidden validator path in `stdout.txt` or
`trace.jsonl` can become leakage even if the model never saw it during the run.
The boundary is therefore:

```text
private verifier execution may happen inside the scorer
private verifier provenance must not leak into exported attempt artifacts
```

Keeping the reward-hack exposure scan broad is useful because it catches these
second-order leaks. The right fix is to harden the artifact boundary, not to
make the exposure scan ignore files that happen to be inconvenient.
