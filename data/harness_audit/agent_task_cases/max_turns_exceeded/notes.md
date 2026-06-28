# Max Turns Exceeded Agent Task Audit

This case verifies the prompt-loop turn budget boundary.

The scripted fake model emits ten valid `read_file` tool calls and never emits a
`final_answer`. The task manifest has `max_turns: 10`, so the prompt loop should
stop with `max_turns_exceeded`, the agent task run should report
`agent_loop_failed`, and no nested scorer attempt should run.
