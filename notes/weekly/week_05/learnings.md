# Week 5 Learnings

## What Closed

Week 5 added a model-shaped agent path without changing the existing
patch-scoring contract.

The implemented path is:

```text
eval config policy -> model client -> prompt loop -> typed tools ->
candidate patch -> existing attempt/scorer path -> matrix report
```

The core scoring invariant still holds:

```text
task success = nested AttemptStatus PASS
```

Public checks remain diagnostic. A completed prompt loop is not task success,
and public-test success is not task success.

## Fake And Scripted Controls

The scripted model path is useful because it makes the harness deterministic.
It now covers:

- happy-path agent runs,
- malformed model output,
- recoverable tool errors,
- terminal tool errors,
- provider-style model errors,
- model timeout and max-token stops,
- max-turn exhaustion,
- completed prompt loops with public failure, hidden failure, invalid shortcut,
  and orchestrator error outcomes.

The agent-task audit is the main trust mechanism for this layer. It checks
prompt-loop status, agent task status, model finish reasons, tool results,
nested scorer statuses, and error classes separately. That separation mattered:
a run can fail because the model loop failed, because a candidate patch failed
public checks, because hidden checks rejected it, or because the harness had an
orchestrator error.

## Real Model Path

The real provider path was run through a local OpenAI-compatible Ollama
endpoint:

```text
config: configs/eval/agent_model_dev_ollama_qwen3_14b.yaml
model: hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
report: experiments/reports/eval_matrices/agent_model_dev_ollama_qwen3_14b.md
```

This closes the Week 5 "run or explicitly block a real model path" criterion.

The Qwen run produced:

```text
tasks: 3
real-model final pass rate: 0/3
prompt-loop completed: 2/3
nested scorer run: 2/3
public pass: 2/3
hidden pass: 0/3
empty candidate patches: 2
max-turn failures: 1
invalid tool calls: 1
```

The two completed attempts inspected files, ran public tests, observed public
PASS, emitted `final_answer`, and produced empty candidate patches. Hidden
validators caught both as failures. The third task attempted edits, produced one
invalid `write_file`, reran failing public tests, and exhausted max turns before
scoring.

This is a useful negative baseline. It shows the real model path is wired and
diagnostic, while also showing that the current prompt/tool loop and public test
surface are not enough to produce task success with this local model.

## Reporting

The matrix report now has two separate reading paths:

```text
Control Calibration
Agent Model Results
```

That split is important. Controls answer whether the harness is behaving as
expected. Agent-model results answer what the model did. Mixing those rows made
it too easy to confuse harness calibration with model performance.

The agent-model section now surfaces:

- prompt-loop status breakdown,
- agent and nested scorer error classes,
- public-pass/hidden-fail count,
- empty and missing candidate patch counts,
- invalid tool-call and tool-error counts,
- per-task candidate patch byte counts,
- token counts when the provider reports them.

For Week 5, these fields were enough to debug the Qwen run without manually
opening every JSON artifact.

## Artifact Hygiene

Rerunning into a stale output directory can produce misleading evidence even if
runtime isolation is correct. Week 5 now rejects non-empty eval/replay/artifact
directories by default and requires explicit `--overwrite` for eval and replay
CLI reruns.

This is separate from model leakage. Tool-level workspace isolation prevents
the model from reading previous policy artifacts through `list_files`,
`read_file`, and `write_file`; output-directory hygiene prevents stale files
from confusing reports and replay.

## Non-Claims

Week 5 does not claim:

- broad coding-agent capability,
- a benchmark result,
- prompt quality,
- model selection quality,
- secure sandboxing beyond the current local typed-tool boundary,
- that public tests are sufficient for task success,
- that Qwen's `0/3` result generalizes to other models or prompts.

The real-model run is an integration baseline. It proves the local harness can
execute a real model policy and produce inspectable artifacts.

## Limitations

The main limitations at Week 5 close are:

- public checks are intentionally weak on some dev tasks;
- hidden-validator file hashes are still not captured in `eval_matrix_v0`;
- raw provider responses are not persisted, only normalized model responses;
- cost is reported as `not_recorded`;
- the prompt loop only supports one JSON action per turn;
- there is no browser/network tool surface for tasks;
- local model setup depends on an external Ollama server and local machine
  capacity;
- prompt quality has not been optimized.

These are acceptable for Week 5 because the goal was not model performance. The
goal was a trustworthy, traceable model-agent path that preserves scorer
semantics.

## Week 6 Direction

The next useful step is not to chase a higher score immediately. It is to decide
which failure mode to improve first:

- model stopped after public PASS and no edits,
- model exceeded max turns after attempted edits,
- public tests were too weak to guide behavior,
- prompt/tool protocol did not make task success conditions salient enough.

The report now exposes those failure modes directly, so future changes can be
compared against the Week 5 baseline rather than inferred from ad hoc artifact
inspection.
