# Malformed JSON Agent Task Audit

This case verifies the malformed model-output boundary.

The scripted fake model emits invalid JSON on the first turn. The prompt loop
should stop with `invalid_model_output`, the agent task run should report
`agent_loop_failed`, no tools should execute, and no nested scorer attempt
should run.
