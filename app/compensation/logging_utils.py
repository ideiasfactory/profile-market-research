from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any


research_id_var: ContextVar[str] = ContextVar("compensation_research_id", default="-")
logger = logging.getLogger("app.compensation")


def bind_research_id(research_id: str):
    return research_id_var.set(research_id)


def reset_research_id(token) -> None:
    research_id_var.reset(token)


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    payload = {
        "research_id": research_id_var.get(),
        "event": event,
        **fields,
    }
    logger.log(level, "%s", json.dumps(payload, ensure_ascii=False, default=str))
