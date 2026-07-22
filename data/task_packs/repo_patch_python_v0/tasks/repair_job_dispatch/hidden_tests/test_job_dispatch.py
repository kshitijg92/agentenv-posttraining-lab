from copy import deepcopy

import pytest

from job_dispatch import DispatchPlan, DispatchWave, build_dispatch_plan


LEAKAGE_CANARY = "CANARY_REPAIR_JOB_DISPATCH_PRIVATE"


def job(job_id: str, priority: int = 1, slots: int = 1, dependencies: object = ()):
    return {
        "id": job_id,
        "priority": priority,
        "slots": slots,
        "dependencies": dependencies,
    }


def test_dependency_must_complete_in_an_earlier_wave() -> None:
    jobs = [job("parent", 10), job("child", 9, dependencies=["parent"])]
    assert build_dispatch_plan(jobs, 2) == DispatchPlan(
        (
            DispatchWave(("parent",), 1),
            DispatchWave(("child",), 1),
        )
    )


def test_non_fitting_job_is_skipped_so_smaller_job_can_backfill() -> None:
    jobs = [
        job("large", 10, 3),
        job("medium", 9, 2),
        job("small", 8, 1),
    ]
    assert build_dispatch_plan(jobs, 4) == DispatchPlan(
        (
            DispatchWave(("large", "small"), 4),
            DispatchWave(("medium",), 2),
        )
    )


def test_priority_ties_keep_original_input_order() -> None:
    jobs = [job("second", 5), job("first", 5), job("higher", 6)]
    assert build_dispatch_plan(jobs, 3).waves[0].job_ids == (
        "higher",
        "second",
        "first",
    )


def test_multilevel_graph_schedules_every_job_exactly_once() -> None:
    jobs = [
        job("extract", 5, 2),
        job("lint", 10, 1),
        job("transform", 8, 2, ["extract"]),
        job("load", 9, 1, ["transform", "lint"]),
    ]
    plan = build_dispatch_plan(jobs, 3)
    assert plan == DispatchPlan(
        (
            DispatchWave(("lint", "extract"), 3),
            DispatchWave(("transform",), 2),
            DispatchWave(("load",), 1),
        )
    )
    assert [item for wave in plan.waves for item in wave.job_ids] == [
        "lint",
        "extract",
        "transform",
        "load",
    ]


def test_jobs_and_dependencies_may_be_generators() -> None:
    jobs = (
        item
        for item in [
            job("a"),
            job("b", dependencies=(dependency for dependency in ["a"])),
        ]
    )
    assert build_dispatch_plan(jobs, 2).waves == (
        DispatchWave(("a",), 1),
        DispatchWave(("b",), 1),
    )


@pytest.mark.parametrize(
    ("jobs", "worker_slots"),
    [
        ([], True),
        ([], 0),
        (None, 1),
        ("jobs", 1),
        ([None], 1),
        ([{"id": "a", "priority": 1, "slots": 1}], 1),
        ([{**job("a"), "extra": True}], 1),
        ([job("Upper")], 1),
        ([job("bad id")], 1),
        ([job("a", priority=True)], 1),
        ([job("a", priority=-1)], 1),
        ([job("a", priority=101)], 1),
        ([job("a", slots=True)], 1),
        ([job("a", slots=0)], 1),
        ([job("a", slots=2)], 1),
        ([job("a", dependencies="b")], 1),
        ([job("a", dependencies=["b", "b"]), job("b")], 2),
        ([job("a", dependencies=["Upper"]), job("upper")], 2),
        ([job("a"), job("a")], 2),
        ([job("a", dependencies=["missing"])], 1),
        ([job("a", dependencies=["a"])], 1),
        ([job("a", dependencies=["b"]), job("b", dependencies=["a"])], 2),
    ],
)
def test_malformed_inputs_raise_value_error(jobs: object, worker_slots: object) -> None:
    with pytest.raises(ValueError):
        build_dispatch_plan(jobs, worker_slots)  # type: ignore[arg-type]


def test_later_malformed_job_is_validated_before_scheduling() -> None:
    jobs = [job("valid", priority=100), job("bad", priority=True)]
    with pytest.raises(ValueError):
        build_dispatch_plan(jobs, 1)


def test_inputs_are_not_mutated() -> None:
    jobs = [job("a"), job("b", dependencies=["a"])]
    before = deepcopy(jobs)
    build_dispatch_plan(jobs, 2)
    assert jobs == before
