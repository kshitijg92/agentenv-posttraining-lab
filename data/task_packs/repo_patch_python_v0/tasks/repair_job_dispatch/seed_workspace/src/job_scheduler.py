from job_models import DispatchPlan, DispatchWave, Job
from job_priority import priority_order
from job_report import make_plan, make_wave


def schedule_jobs(jobs: list[Job], worker_slots: int) -> DispatchPlan:
    pending = list(jobs)
    completed: set[str] = set()
    waves: list[DispatchWave] = []
    while pending:
        selected: list[Job] = []
        selected_ids: set[str] = set()
        remaining = worker_slots
        for job in priority_order(pending):
            if not set(job.dependencies).issubset(completed | selected_ids):
                continue
            if job.slots > remaining:
                break
            selected.append(job)
            selected_ids.add(job.job_id)
            remaining -= job.slots
        if not selected:
            raise ValueError("cannot make scheduling progress")
        waves.append(make_wave(selected))
        completed.update(selected_ids)
        pending = [job for job in pending if job.job_id not in selected_ids]
    return make_plan(waves)
