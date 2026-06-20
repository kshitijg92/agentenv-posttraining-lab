# Week 1 Notes

## Focus

This week I am building one repo-patch task end to end.

The goal is not to build a full benchmark yet. The goal is to understand the minimum contract between:

- a task manifest,
- an initial workspace,
- public checks,
- hidden validators,
- oracle and bad controls,
- attempt/scoring output,
- traceability.

By the end of the week, I want one task where an oracle patch passes, a no-op patch fails, and a public-only patch can pass visible checks while failing hidden validation.

## References To Read

I should keep this reading pass short, roughly 60-90 minutes total. I am reading to extract design constraints for my local artifact, not to survey the whole eval ecosystem.

### Inspect AI

- Tasks: https://inspect.aisi.org.uk/tasks.html
- Scorers: https://inspect.aisi.org.uk/scorers.html

What I am looking for:

- how a task is separated from a solver or agent,
- how scoring is represented as a separate component,
- what information belongs in the task definition versus the result log,
- how Inspect thinks about eval logs and scorer outputs.

Design implication for this repo:

My Week 1 loop should keep task loading, patch application, orchestration, and scoring as separate concepts, even if the implementation is tiny.

### Harbor / Terminal-Bench

- Task structure: https://www.harborframework.com/docs/tasks
- Terminal-Bench example task: https://www.tbench.ai/registry/terminal-bench-core/head/build-linux-kernel-qemu

What I am looking for:

- the shape of an agent-facing instruction,
- the role of an oracle solution,
- how tests become a reward or pass/fail signal,
- how verifier files are kept separate from the agent phase,
- what metadata and timeouts are useful even for small tasks.

Design implication for this repo:

My hidden tests should not be in `workspace_seed`. The hidden scorer should only run them after the patch phase.

### METR Task Standard

- Overview: https://github.com/METR/task-standard
- Standard: https://raw.githubusercontent.com/METR/task-standard/main/STANDARD.md

What I am looking for:

- the lifecycle of environment setup, instructions, agent run, and scoring,
- what data is private task data versus agent-visible instruction,
- how task families and controls help test the validity of the task itself.

Design implication for this repo:

The task manifest can be small, but it should be explicit about limits, hidden validators, controls, and what private eval-side data the orchestrator/scorer is allowed to inspect.

### SWE-bench

- Evaluation guide: https://www.swebench.com/SWE-bench/guides/evaluation/

What I am looking for:

- the basic patch-evaluation contract,
- the prediction format idea: instance id plus generated patch,
- the distinction between completed runs and resolved instances,
- what result artifacts are useful for debugging failures.

Design implication for this repo:

My `agentenv attempt run` command should distinguish patch apply errors, public test failures, hidden test failures, timeouts, orchestrator errors, and scorer errors instead of collapsing everything into pass/fail.

## Questions To Answer After Reading

- What does my first toy task measure?
- What does it not measure?
- Why is the hidden validator hidden?
- How can a public-only patch fool the public tests?
- What fields are missing from the first trace format?
- What would make this task too toy to learn from?

## Self-Deception Traps

- If the oracle passes but there are no known-bad controls, I have not tested the eval harness.
- If the public-only patch fails public tests, it is not a useful public-only control.
- If hidden tests are present in `workspace_seed`, the task does not test hidden validation discipline.
- If all failures are reported as `FAIL`, I will not know whether I built a task failure, scorer failure, orchestrator failure, environment failure, or patch failure.
- If I add multiple tasks before one task is audited, I am scaling uncertainty instead of learning the loop.
