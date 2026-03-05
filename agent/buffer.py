"""
agent/buffer.py — thread-safe event ring buffer + periodic flush.

Single responsibility: accumulate events and push batches to the API.
"""

import threading
import time
from collections import deque
from typing import Callable

FLUSH_INTERVAL = 0.2  # seconds

_buf: deque = deque()
_lock = threading.Lock()


def push(event: dict) -> None:
    """Append one event to the buffer (called from listener threads)."""
    with _lock:
        _buf.append(event)


def flush(session_id: int | None, post_fn: Callable) -> None:
    """Drain the buffer and POST the batch. No-op if empty."""
    if not _buf:
        return
    with _lock:
        batch = list(_buf)
        _buf.clear()
    post_fn("/api/ingest", {"session_id": session_id, "events": batch})


def flush_loop(
    session_id_getter: Callable[[], int | None],
    post_fn: Callable,
    stop_event: threading.Event,
) -> None:
    """Background thread: flush every FLUSH_INTERVAL seconds until stopped."""
    while not stop_event.is_set():
        time.sleep(FLUSH_INTERVAL)
        flush(session_id_getter(), post_fn)
