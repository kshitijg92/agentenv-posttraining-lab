# Completed Public Fail Agent Task Audit

This case verifies nested scorer wiring for a public-test failure after a
completed prompt loop.

The scripted fake model replaces `normalize_ratio` with a constant return value,
runs the public check, then emits `final_answer`. The prompt loop should complete
and the nested scorer should report `PUBLIC_TEST_FAIL`.
