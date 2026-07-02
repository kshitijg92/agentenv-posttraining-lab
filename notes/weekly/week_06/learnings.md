# Week 6 Learnings

Week 6 is about making the eval loop trustworthy enough that later trajectory,
reward, and data-filtering work does not build on weak evidence.

The central lesson is that an eval result is not just a score. It is a claim
that a specific task, split, policy, prompt, tool protocol, scorer, and artifact
surface all stayed stable enough for the score to mean something.

## Measurement Claim

`repo_patch_python_v0` currently measures a narrow compound capability:

```text
small Python repair ability + ability to follow the lab's strict agent/tool
interface
```

The tasks are small localized Python repository repairs, usually one to two
files and a few functions. Success means producing a patch through the agent
loop that passes hidden behavioral tests.

This does not measure broad software engineering, architecture design, large
refactors, production debugging, UI work, multi-service reasoning, or general
coding-agent capability.

The strict interface caveat matters. A model can have useful coding ability and
still fail this lab if it cannot emit exactly one valid JSON action per turn.
The DeepSeek R1 Distill Qwen probe made this concrete: the model endpoint
worked and the first tool call could be valid, but reasoning/prose artifacts
after tool results broke the current protocol. Calling that unsupported is more
honest than weakening the parser and changing the eval contract midstream.

## Why Splits Matter

Splits are not bookkeeping. They define what evidence is allowed to influence
what decisions.

If a task appears in two splits, or if `task.yaml` disagrees with
`splits.lock.json`, then eval results can quietly mix practice, dev, and heldout
evidence. That makes later claims about generalization or filtering untrustworthy.

The split lock is a provenance boundary:

- every task must belong to exactly one split;
- task YAML split metadata must match the lock;
- the lock cannot refer to unknown tasks;
- duplicate task IDs are invalid.

## Why Hashes Matter

Task hashes are drift evidence. They do not prove a task is good, but they make
it much harder to accidentally trust results from a different task version.

The most important design choice was eval-scoped task hashing:

```text
eval comparability is based on selected tasks, not the whole task pack
```

If a task pack gains a new unused task, an old eval over unchanged selected
tasks should not be invalidated. The selected-task hash set is the meaningful
comparison key for eval runs.

Per-file hashes matter because a single aggregate hash can say that something
changed but not where. The manifest should carry enough structured detail that
drift can be debugged without bloating human reports.

## Why Control Flake Detection Matters

Semantic control status is not enough. A control can keep the same final status
while deterministic artifacts drift underneath it.

For controls, a repeat run is stable only if later repeats match repeat 0 after
normalizing expected volatile evidence. One mismatch in many repeats is still a
failure, because it means the system can produce different evidence for the same
control path.

The scorer and agent control layers need different but parallel treatment:

- scorer controls compare scorer attempt artifacts;
- agent controls compare the full agent artifact tree;
- agent controls that reach scoring also compare nested `attempt/*` artifacts;
- prompt-loop-only agent controls compare only the agent-level artifact surface.

Repeat 0 defines the artifact surface. If later repeats add, remove, or change
files relative to repeat 0, that is drift.

## Normalization Lessons

Normalization should remove run-local noise, not real behavioral evidence.

Good volatile fields to normalize include:

- run IDs and attempt IDs;
- timestamps and durations;
- model latency;
- stdout/stderr byte counts;
- repo-local absolute paths;
- generated `/tmp/agentenv-*` paths;
- pytest temp paths, including ellipsized forms.

The `...ytest-N` pytest rendering bug was a useful reminder that normalization
contracts are empirical. You only know which fields are volatile after repeated
runs expose the noise.

The self-deception trap is over-normalizing. If normalization erases behavior
that should be stable, flake detection becomes a false reassurance tool.

## Report Versus Manifest

Markdown reports are for humans. JSON manifests are for evidence and tools.

The control report should summarize:

- overall flake status;
- scorer flake status;
- agent flake status;
- groups checked and drifted groups.

The manifest should carry per-file hashes and drift details. Dumping hashes into
Markdown makes the report look rigorous while making it harder to read.

## Trajectory Readiness

Trajectory export will eventually turn eval artifacts into data rows containing
the task, policy, prompt, model actions, tool results, candidate patch, scorer
outcome, and provenance.

But exported trajectories are not automatically training data. They become
candidate training or reward data only after filtering for:

- split/provenance correctness;
- task hash stability;
- hidden-scorer validity;
- control repeatability;
- leakage risk;
- flake risk;
- usefulness for the intended training objective.

The Week 6 work protects that future boundary. Without it, trajectory export
would only make bad evidence easier to reuse.

## Current Limitation

The current task pack is intentionally small. It is useful for testing the lab
loop and narrow Python repair behavior, not for making broad claims about model
coding ability.

Any future report should state the compound construct clearly:

```text
small localized Python repair under a strict JSON-action tool interface
```

That is the honest claim until the task distribution, tool protocol, and model
interface broaden deliberately.
