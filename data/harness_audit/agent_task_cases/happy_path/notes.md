# Happy Path Agent Task Audit

This is the positive-control agent-task audit case for `toy_python_fix_001`.

The scripted fake model reads `src/mathlib.py`, writes the oracle fix, runs the
public test command, and returns a final answer. The harness should classify the
agent task run as `scored`, the prompt loop as `completed`, and the nested
scorer attempt as `PASS` for final, public, and hidden statuses.

This case audits the harness boundary, not model quality.
