from __future__ import annotations

import asyncio
from typing import TypeVar

import anyio


T = TypeVar("T")


async def await_task_resiliently(task: asyncio.Task[T]) -> T:
    """Wait for a task to settle before propagating caller cancellation."""
    first_cancellation: asyncio.CancelledError | None = None

    while True:
        try:
            if first_cancellation is None:
                result = await asyncio.shield(task)
            else:
                with anyio.CancelScope(shield=True):
                    result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as exc:
            if task.cancelled():
                if first_cancellation is not None:
                    raise first_cancellation
                raise
            if first_cancellation is None:
                first_cancellation = exc
            if task.done():
                break
        except BaseException:
            if first_cancellation is None:
                raise
            break

    if first_cancellation is not None:
        if not task.cancelled():
            task.exception()
        raise first_cancellation
    return result


__all__ = ["await_task_resiliently"]
