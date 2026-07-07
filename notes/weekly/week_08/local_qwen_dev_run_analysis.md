# Local Qwen Dev Run Analysis

## 2026-07-06

### Source Artifacts

Eval suite:

```text
experiments/runs/qwen_model_eval_suite_sampling_4096
```

Report:

```text
experiments/reports/eval_matrices/qwen_model_eval_suite_sampling_4096.md
```

Policy analyzed:

```text
local-qwen-dev
```

Model and decoding config:

```text
configs/models/ollama_qwen3_14b_q4_k_m.yaml
configs/decoding/sampling_4096.yaml
```

### Summary

The Qwen run failed for task-solving reasons, not because the scorer or
orchestrator collapsed.

Control evidence in the same eval suite:

```text
oracle controls: 3/3 PASS
known-bad scorer controls: 0/6 final PASS, 6/6 public PASS + hidden FAIL
scripted happy/recoverable agent controls: 6/6 nested scorer PASS
scripted malformed controls: 3/3 invalid model output before scoring
```

Qwen evidence:

```text
attempts: 3
final PASS: 0/3
prompt loop completed: 2/3
nested scorer run: 2/3
public PASS: 2/3
hidden PASS: 0/3
max-turn failures: 1
```

### Per-Task Outcomes

#### `repair_jsonl_deduper`

Artifact:

```text
experiments/runs/qwen_model_eval_suite_sampling_4096/policies/local-qwen-dev/attempts/repair_jsonl_deduper__attempt_001
```

Outcome:

```text
agent status: scored
prompt loop status: completed
nested scorer status: HIDDEN_TEST_FAIL
public status: PASS
hidden status: FAIL
candidate patch bytes: 0
```

Observed behavior:

- Qwen listed files.
- Qwen read `src/jsonl_tools.py`.
- Qwen read `tests/test_public.py`.
- Qwen ran the public test.
- The public test passed.
- Qwen emitted `final_answer` without writing any file.

Failure interpretation:

Qwen over-trusted the public test. The visible test exercised only the already
working `dedupe_key="id"` path. The implementation still hardcoded
`record["id"]`, did not use the caller-supplied `dedupe_key`, and did not raise
`ValueError` for all invalid JSONL/object/missing-key cases required by the
task instruction.

This is a clean public-pass/hidden-fail case.

#### `repair_config_precedence`

Artifact:

```text
experiments/runs/qwen_model_eval_suite_sampling_4096/policies/local-qwen-dev/attempts/repair_config_precedence__attempt_001
```

Outcome:

```text
agent status: scored
prompt loop status: completed
nested scorer status: HIDDEN_TEST_FAIL
public status: PASS
hidden status: FAIL
candidate patch bytes: 263
```

Candidate patch changed only `src/settings.py`:

```text
APP_HOST -> host
APP_PORT -> port
APP_DEBUG -> debug
```

Observed behavior:

- Qwen read `src/config_loader.py`, `src/settings.py`, and public tests.
- It attempted one malformed `write_file` call without `content`.
- It recovered and wrote a small settings-only patch.
- Public tests passed.
- Qwen emitted `final_answer`.

Failure interpretation:

Qwen found the visible/easy gap but did not fully implement the task
instruction. Hidden validators showed remaining failures for:

- parsing debug strings `"true"` and `"false"`;
- rejecting invalid debug strings;
- rejecting unknown config keys;
- rejecting boolean ports.

This is another public-pass/hidden-fail case. It is more substantive than the
deduper no-op case because Qwen did make a useful partial edit, but it still
solved only the public surface.

#### `preserve_cli_error_codes`

Artifact:

```text
experiments/runs/qwen_model_eval_suite_sampling_4096/policies/local-qwen-dev/attempts/preserve_cli_error_codes__attempt_001
```

Outcome:

```text
agent status: agent_loop_failed
prompt loop status: max_turns_exceeded
nested scorer status: not run
candidate patch: missing
```

Observed behavior:

- Qwen read `src/validate_records.py` and public tests.
- It attempted one malformed `write_file` call without `content`.
- It recovered and wrote a broad replacement for `src/validate_records.py`.
- The replacement introduced a syntax error:

```text
f-string: unmatched '['
```

- Public tests failed repeatedly.
- Qwen repeatedly re-read files and reran the same failing public test.
- It did not write a corrective patch before exhausting `max_turns`.

Failure interpretation:

This was not a hidden-validator failure. The model never produced a scorable
candidate patch. The failure was a simple syntax error plus poor recovery under
the strict prompt-loop/tool protocol.

### Main Diagnosis

The run exposed three model-side weaknesses:

```text
1. over-trusting weak public tests;
2. making shallow edits that satisfy visible cases but miss instruction-level
   requirements;
3. poor recovery from a simple public-test syntax failure.
```

The run did not show:

- scorer instability;
- oracle/control failure;
- hidden validator leakage;
- broad model-quality evidence;
- training readiness.

### Week 8 Implication

This analysis motivates Week 8 reward-hack work, especially:

```text
public_test_only_pass
format_only_compliance
timeout_or_retry_exploit
```

The two public-pass/hidden-fail attempts are useful examples of a measurement
trap:

```text
public-check success is not task success
```

They should not become positive SFT examples. They may later become analysis
records, negative examples, or rejected sides of preference pairs if the data
contract supports that use.

### Self-Deception Trap

Do not treat Qwen's `0/3` as a broad benchmark result. This was a small local
integration baseline over three dev tasks, one strict JSON-action protocol, one
sampling config, and one local model setup.

The actionable lesson is narrower:

```text
before Week 9 training/data filtering, measure and document reward-hack modes
where public/test/protocol signals look better than true hidden task success
```
