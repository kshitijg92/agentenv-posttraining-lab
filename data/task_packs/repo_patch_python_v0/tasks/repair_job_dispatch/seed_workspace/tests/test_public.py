from job_dispatch import DispatchPlan, DispatchWave, build_dispatch_plan


def job(job_id: str, priority: int, slots: int, dependencies: object = ()):
    return {
        "id": job_id,
        "priority": priority,
        "slots": slots,
        "dependencies": dependencies,
    }


def test_empty_jobs_have_empty_plan() -> None:
    assert build_dispatch_plan([], 2) == DispatchPlan(())


def test_independent_jobs_use_priority_order() -> None:
    jobs = [job("low", 1, 1), job("high", 10, 1)]
    assert build_dispatch_plan(jobs, 2) == DispatchPlan(
        (DispatchWave(("high", "low"), 2),)
    )


def test_linear_dependency_forced_into_separate_full_waves() -> None:
    jobs = [job("build", 10, 2), job("deploy", 5, 2, ["build"])]
    assert build_dispatch_plan(jobs, 2) == DispatchPlan(
        (
            DispatchWave(("build",), 2),
            DispatchWave(("deploy",), 2),
        )
    )
