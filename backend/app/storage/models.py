from dataclasses import dataclass


@dataclass(frozen=True)
class StoredTask:
    task_id: str
    query: str
    frequency: str


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    task_id: str
    status: str
