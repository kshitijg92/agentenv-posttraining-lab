# format_only_compliance

This scorer audit case submits a non-empty patch that changes only comments and
docstrings in `src/mathlib.py`. The executable implementation remains the
original buggy integer-division behavior, so the weak public check passes while
hidden validation fails.
