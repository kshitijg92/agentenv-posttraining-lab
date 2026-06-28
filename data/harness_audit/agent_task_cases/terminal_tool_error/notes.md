# Terminal Tool Error Agent Task Audit

This case verifies terminal tool-error handling after prior successful tool
calls.

The scripted fake model performs two valid `read_file` calls, then tries to read
`../outside.py`. The local tool layer should reject that path with `UnsafePath`,
the prompt loop should stop with `terminal_tool_error`, the fourth scripted step
should not run, and no nested scorer attempt should run.
