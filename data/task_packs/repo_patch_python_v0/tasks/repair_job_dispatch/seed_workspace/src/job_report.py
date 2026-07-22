from job_models import DispatchPlan, DispatchWave, Job


def make_wave(jobs: list[Job]) -> DispatchWave:
    return DispatchWave(
        job_ids=tuple(job.job_id for job in jobs),
        slots_used=sum(job.slots for job in jobs),
    )


def make_plan(waves: list[DispatchWave]) -> DispatchPlan:
    return DispatchPlan(waves=tuple(waves))
