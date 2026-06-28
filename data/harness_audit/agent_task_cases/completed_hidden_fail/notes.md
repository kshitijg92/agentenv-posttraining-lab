# Completed Hidden Fail Agent Task Audit

This case verifies nested scorer wiring for a hidden-test failure after a
completed prompt loop.

The scripted fake model changes `normalize_ratio` to keep floor-division
semantics while casting the public example result to `float`. The public check
passes, the prompt loop completes, the agent task run invokes the nested scorer,
and the nested scorer should report `HIDDEN_TEST_FAIL`.
