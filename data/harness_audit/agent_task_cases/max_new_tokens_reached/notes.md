# max_new_tokens_reached

This case emits a `final_answer`-shaped payload with
`finish_reason = max_new_tokens_reached`.

It expects the prompt loop to fail before parsing the otherwise valid JSON,
running tools, or starting a nested scorer attempt.
