from collections.abc import Iterable

from job_graph import validate_graph
from job_models import DispatchPlan, DispatchWave
from job_scheduler import schedule_jobs
from job_validation import parse_jobs


def build_dispatch_plan(jobs: Iterable[object], worker_slots: int) -> DispatchPlan:
    parsed = parse_jobs(jobs, worker_slots)
    validate_graph(parsed)
    return schedule_jobs(parsed, worker_slots)


__all__ = ["DispatchPlan", "DispatchWave", "build_dispatch_plan"]
