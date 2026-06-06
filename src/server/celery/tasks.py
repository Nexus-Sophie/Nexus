from __future__ import annotations

import asyncio
import uuid

from src.logger import logger
from src.server.celery.app import celery_app
from src.server.celery.execution import execute_agent_task


@celery_app.task(bind=True, name="nexus.execute_agent_task")
def run_agent_task(
    self,
    task_id: str,
    **legacy_kwargs: object,
) -> None:
    """Run an agent task from Celery."""
    # Accept ignored kwargs so older queued messages can still deserialize after
    # the worker has been upgraded.
    del legacy_kwargs
    try:
        delivery_info = getattr(self.request, "delivery_info", {}) or {}
        redelivered = bool(delivery_info.get("redelivered"))
        asyncio.run(
            execute_agent_task(
                task_id=uuid.UUID(task_id),
                allow_running=redelivered,
            )
        )
    except Exception as exc:
        logger.exception(
            "Celery worker failed to execute task_id=%s: %s",
            task_id,
            str(exc),
        )
        raise
