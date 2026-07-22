from collections.abc import Iterable, Mapping

from job_models import Job


def parse_jobs(raw_jobs: Iterable[object], worker_slots: int) -> list[Job]:
    if not isinstance(worker_slots, int) or worker_slots <= 0:
        raise ValueError("worker_slots must be positive")
    if isinstance(raw_jobs, (str, bytes)):
        raise ValueError("jobs must be a non-string iterable")
    try:
        materialized = list(raw_jobs)
    except TypeError as exc:
        raise ValueError("jobs must be iterable") from exc

    jobs: list[Job] = []
    for index, raw in enumerate(materialized):
        if not isinstance(raw, Mapping):
            raise ValueError("job must be a mapping")
        try:
            jobs.append(
                Job(
                    job_id=str(raw["id"]),
                    priority=int(raw["priority"]),
                    slots=int(raw["slots"]),
                    dependencies=tuple(raw.get("dependencies", ())),
                    input_index=index,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid job") from exc
    return jobs
