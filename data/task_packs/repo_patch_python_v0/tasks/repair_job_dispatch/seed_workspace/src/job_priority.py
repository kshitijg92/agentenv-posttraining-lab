from job_models import Job


def priority_order(jobs: list[Job]) -> list[Job]:
    return sorted(jobs, key=lambda job: (-job.priority, job.input_index))
