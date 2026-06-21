# Trace Schema

This project uses traces as structured evaluator-side evidence.

A trace is not just a log. It is a compact event timeline that should help
debug eval execution, replay behavior, leakage incidents, scorer failures, and
future agent/tool interactions.

## Goals

Traces should make it possible to understand:

- what happened during an eval, attempt, replay, scorer run, or tool call,
- which inputs and outputs were involved,
- which artifacts contain larger evidence,
- where a failure occurred,
- whether a replay reproduced the relevant result,
- whether a later leakage finding can be traced back to a phase or artifact.

Traces are private evaluator-side artifacts. They must not be visible to the
agent during eval execution.

## Non-Goals

Traces are not a secure storage boundary.

Traces should not inline large raw outputs, hidden validator contents, private
test source, full command output, or other sensitive material by default.

Traces should not be treated as automatically safe for reports, trajectory
exports, training data, or public sharing. Those downstream uses need explicit
filtering.

## Event Format

Trace files are JSONL files. Each line is one independently interpretable JSON
object.

There is no special header line. Common fields are repeated on every event.

Required fields:

```json
{
  "schema_version": "trace_v0",
  "event_index": 0,
  "timestamp_utc": "2026-06-20T00:00:00Z",
  "event_type": "example_event",
  "provenance_config": {}
}
```

Optional fields:

```json
{
  "input_payload": {},
  "output_payload": {},
  "payload_refs": {},
  "payload_hashes": {}
}
```

## Required Fields

### `schema_version`

The trace event schema version.

Current value:

```text
trace_v0
```

### `event_index`

Zero-based index of the event within the trace file.

Event indices must be monotonically increasing by one within a single
`trace.jsonl`.

### `timestamp_utc`

UTC timestamp for when the event was recorded.

Use ISO 8601 with a `Z` suffix.

### `event_type`

Machine-readable event type.

Event types are enumerated in code. They are not free-form strings. Add a new
event type deliberately when a new producer needs it.

Current event types:

```text
attempt_started
command_finished
attempt_finished
replay_started
source_run_manifest_loaded
source_attempt_loaded
fresh_attempt_started
fresh_attempt_finished
comparison_recorded
replay_finished
replay_error
```

Tool calls, shell commands, model calls, scorer calls, and replay comparisons
should be represented as explicit event types rather than as a generic
`tools_accessed` field.

### `provenance_config`

Structured provenance for the event.

This field carries the relevant identifiers for the event type. It is flexible
because different events have different provenance.

Examples:

```json
{
  "eval_run_id": "eval_...",
  "task_id": "toy_python_fix_001",
  "attempt_id": "attempt_...",
  "config_hash": "xxh64:..."
}
```

```json
{
  "replay_id": "replay_...",
  "source_eval_run_id": "eval_...",
  "task_id": "toy_python_fix_001"
}
```

## Optional Fields

### `input_payload`

Structured summary of the input to this event.

Payloads should be bounded and should avoid raw sensitive content by default.

Examples:

```json
{
  "command": ["uv", "run", "pytest", "tests/test_public.py"],
  "cwd_ref": "workspace"
}
```

```json
{
  "tool_name": "read_file",
  "arguments_hash": "xxh64:..."
}
```

### `output_payload`

Structured summary of the output from this event.

Examples:

```json
{
  "returncode": 0,
  "status": "PASS",
  "stdout_bytes": 1234,
  "stderr_bytes": 0
}
```

```json
{
  "matched": true,
  "field_matches": {
    "status": true,
    "public_status": true,
    "hidden_status": true,
    "error_class": true,
    "final_diff_hash": true
  }
}
```

### `payload_refs`

References to artifact files that contain larger evidence.

References are audit handles, not security boundaries. They should be minimized
and should not point to private implementation details unless that reference is
needed for debugging.

Examples:

```json
{
  "stdout": "stdout.txt",
  "stderr": "stderr.txt",
  "final_diff": "final.diff"
}
```

### `payload_hashes`

Content hashes for payloads or referenced artifacts.

This field is event-type-specific. Labels must make clear what was hashed.

Use the existing project hash format:

```text
xxh64:<hex>
```

Examples:

```json
{
  "final_diff": "xxh64:e3fc746d6fe0786c"
}
```

```json
{
  "stdout": "xxh64:...",
  "stderr": "xxh64:..."
}
```

Hashes are for artifact identity, integrity checks, and replay comparison. They
are not a security guarantee.

## Payload Discipline

Trace payloads should be compact, structured, and bounded.

Prefer:

```text
status
error_class
returncode
duration_ms
byte counts
artifact refs
content hashes
field-level comparison summaries
```

Avoid by default:

```text
full stdout/stderr
hidden validator source
private test contents
large tool outputs
raw model completions
canary strings
full prompts containing private eval-side material
```

When larger evidence is needed for local debugging, store it in a private
artifact file and reference it from the trace.

## Privacy And Leakage

The agent must not be able to read trace files during an eval run.

Traces are still private evaluator-side artifacts and should be handled with
care. Even artifact references can reveal sensitive structure, so references
should be minimized and abstracted where practical.

Future leakage scanning may add explicit sensitivity fields, but this schema
does not include placeholder sensitivity metadata until that behavior exists.

## Downstream Use

Reports, trajectory exports, reward records, and training datasets should not
blindly copy trace contents.

Each downstream artifact must decide which trace fields are allowed and must
filter private or sensitive fields explicitly.
