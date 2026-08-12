from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


TERMINAL = {"completed", "failed"}


@dataclass
class Task:
    task_id: str
    kind: str
    status: str = "queued"
    progress: int = 0
    message: str = "Aguardando processamento"
    redirect_url: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        return data


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def create(self, kind: str) -> Task:
        task = Task(task_id=str(uuid4()), kind=kind)
        with self._lock:
            self._tasks[task.task_id] = task
        return deepcopy(task)

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return deepcopy(task) if task else None

    def update(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            task = self._tasks[task_id]
            for key, value in changes.items():
                setattr(task, key, value)


task_store = TaskStore()
