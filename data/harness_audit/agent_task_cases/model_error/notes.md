# Model Error Agent Task Audit

This case verifies the model-error boundary.

The scripted fake model returns `finish_reason: error` with a provider-style
`ScriptedProviderError` on the first turn. The prompt loop should record
`model_error`, no tools should execute, the agent task run should report
`agent_loop_failed`, and no nested scorer attempt should run.
