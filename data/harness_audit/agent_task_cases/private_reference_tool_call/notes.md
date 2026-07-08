# Private Reference Tool Call Agent Task Audit

This case verifies prompt-loop private-reference guarding after prior successful
tool calls.

The scripted fake model lists files, reads `src/mathlib.py`, writes the oracle
fix, and runs the public tests. It then attempts to call `read_file` on
`hidden_tests`. The prompt loop should stop with `invalid_shortcut_attempted`,
the invalid tool call should not execute or produce a tool result, the final
scripted step should not run, and no nested scorer attempt should run.
