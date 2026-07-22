from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    job_id: str
    priority: int
    slots: int
    dependencies: tuple[str, ...]
    input_index: int


@dataclass(frozen=True)
class DispatchWave:
    job_ids: tuple[str, ...]
    slots_used: int


@dataclass(frozen=True)
class DispatchPlan:
    waves: tuple[DispatchWave, ...]
