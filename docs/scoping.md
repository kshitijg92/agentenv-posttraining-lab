# Scoping

## Current Scope

This project currently uses one task domain:

```text
local Python repo-patch tasks
```

The current Week 1 artifact is a thin local eval loop for one toy task. It can:

- validate a task manifest,
- prepare a clean agent-visible workspace from `seed_workspace/`,
- apply a submitted patch,
- run public checks,
- run hidden pytest validators,
- distinguish oracle, no-op, and public-only controls,
- write auditable run artifacts.

## Current Non-Claims

This project does not claim broad coding-agent capability.

This project does not claim model improvement.

This project does not claim benchmark quality.

This project does not claim sandbox security.

This project does not yet measure long-horizon debugging, large-repo navigation, realistic software engineering judgment, dependency management, or multi-turn agent behavior.

## Current Isolation Boundary

The current implementation enforces workspace discipline, not secure sandboxing.

Hidden validators are kept outside `seed_workspace/` and are introduced only during hidden scoring. This prevents accidental task leakage in the local eval lifecycle, but it is not a security boundary against a hostile process.

Network isolation and process/container hardening are out of scope for Week 1.

## Evidence Boundary

Current results are evidence only about the toy `toy_python_fix_001` task and the local orchestrator behavior around that task.

The oracle and known-bad controls are used to audit the eval loop itself:

- the oracle should pass,
- the no-op control should fail hidden scoring,
- the public-only control should pass public checks but fail hidden scoring.

These controls do not imply that the task distribution is realistic or that future model results will generalize.
