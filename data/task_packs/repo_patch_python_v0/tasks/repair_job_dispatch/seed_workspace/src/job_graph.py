from job_models import Job


def validate_graph(jobs: list[Job]) -> None:
    job_ids = {job.job_id for job in jobs}
    for job in jobs:
        if job.job_id in job.dependencies:
            raise ValueError("job cannot depend on itself")
        if not set(job.dependencies).issubset(job_ids):
            raise ValueError("unknown dependency")

    dependencies = {job.job_id: set(job.dependencies) for job in jobs}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(job_id: str) -> None:
        if job_id in visiting:
            raise ValueError("dependency cycle")
        if job_id in visited:
            return
        visiting.add(job_id)
        for dependency in dependencies[job_id]:
            visit(dependency)
        visiting.remove(job_id)
        visited.add(job_id)

    for job_id in dependencies:
        visit(job_id)
