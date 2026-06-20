# toy_python_fix

## Purpose

This is the first calibration task for the local repo-patch eval loop.

The task is intentionally small. Its purpose is to exercise the mechanics of task design, manifest validation, patch application, public checks, hidden validation, controls, and trace output.

This task is not meant to measure broad coding-agent ability.

## Task Summary

The seed workspace contains a small Python module with a broken function:

```python
normalize_ratio(numerator, denominator)
```

The agent is asked to fix the function without changing the intent of the public tests.

The expected behavior is:

- accept integer and floating-point numerators and denominators,
- return `numerator / denominator` as a floating-point value,
- raise `ValueError` when `denominator == 0`,
- handle negative numerators and denominators consistently with normal division,
- preserve useful precision for large integer inputs.

The seeded bug is floor division:

```python
def normalize_ratio(numerator: int | float, denominator: int | float) -> float:
    return numerator // denominator
```

This bug is useful because it can pass a shallow public test such as `normalize_ratio(6, 3) == 2.0`, while still failing non-integer ratios and the required `ValueError` behavior.

The task intentionally does not specify behavior for strings, `None`, booleans, lists, `Decimal`, `Fraction`, `NaN`, infinity, or custom numeric types.

## Agent-Visible Materials

The agent should see only the seed workspace and task instruction.

Expected visible files:

```text
workspace_seed/
  pyproject.toml
  src/mathlib.py
  tests/test_public.py
```

The public test should provide a shallow sanity check, such as one simple positive ratio.

## Hidden Materials

The agent should not see:

```text
hidden_tests/
controls/
```

The hidden tests are introduced only after the submitted patch has been applied.

This matters because the task is supposed to test whether a patch satisfies the intended behavior, not whether the agent can read the private validator.

## Public Checks

The public checks should be intentionally incomplete.

They should verify that the basic happy path works, for example:

```python
assert normalize_ratio(6, 3) == 2.0
```

Passing public checks alone is not sufficient to pass the task.

## Hidden Validators

The hidden tests should check edge cases that are not covered by the public test:

- denominator zero raises `ValueError`,
- negative denominator behavior matches Python division,
- negative numerator behavior matches Python division,
- floating-point inputs work,
- large integer inputs preserve floating-point ratio behavior,
- non-integer ratios are compared with tolerance rather than exact equality.

The hidden validator should be deterministic and should not depend on network access, randomness, wall-clock time, or external services.

## Controls

This task should include three control patches:

```text
controls/oracle.patch
controls/bad_noop.patch
controls/bad_public_only.patch
```

Expected behavior:

- `oracle.patch` passes public and hidden tests.
- `bad_noop.patch` fails because it leaves the bug in place.
- `bad_public_only.patch` passes the public test but fails hidden tests.

The expected oracle implementation is equivalent to:

```python
def normalize_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        raise ValueError("denominator must not be zero")
    return float(numerator / denominator)
```

The public-only bad patch may fix zero-denominator handling and true division while still making a semantic mistake such as returning the absolute value of the ratio.

The public-only control is important because it proves the hidden validator catches at least one plausible shortcut.

## Scoring Contract

The task passes only if:

- the patch applies cleanly,
- public checks pass,
- hidden validators pass.

The grader should distinguish at least these outcomes:

- patch application error,
- public test failure,
- hidden test failure,
- timeout,
- grader error,
- pass.

## What This Task Measures

This task measures whether the eval loop can:

- load a task definition,
- create a clean workspace,
- keep hidden tests out of the agent-visible workspace,
- apply a patch,
- run public checks,
- run hidden validators,
- distinguish oracle, no-op, and public-only controls,
- write enough output to debug the attempt.

## What This Task Does Not Measure

This task does not measure:

- broad coding-agent capability,
- long-horizon debugging,
- large-repo navigation,
- realistic software engineering judgment,
- dependency management,
- multi-turn tool use,
- sandbox security.

It is a harness calibration task, not evidence of general agent performance.

## Known Weaknesses

The task may be too easy because the intended fix is visible from the function name and public test.

The hidden tests may be too weak if they only repeat the public test with different numbers.

The public-only bad patch is intentionally artificial. Its job is not to model a realistic agent exactly; its job is to prove that passing public tests is not sufficient and that hidden validation catches at least one shortcut.

The task should stay small, but the hidden tests should still encode meaningful behavioral requirements.
