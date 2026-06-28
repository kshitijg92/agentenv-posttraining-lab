# model_timeout

This case emits a scripted model response with `finish_reason = timeout` and
`error_class = ScriptedModelTimeout`.

It expects the prompt loop to fail before parsing model output, running tools, or
starting a nested scorer attempt.
