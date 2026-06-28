# Tool Recovery Agent Task Audit

This case verifies recoverable tool-error handling.

The scripted fake model first calls `read_file` without the required `path`
argument. The prompt loop should record an `InvalidToolInput` tool result,
continue, run the corrected read/write/test sequence, and then score the
candidate patch as `PASS`.
