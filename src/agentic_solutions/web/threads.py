"""In-memory record of conversation threads and which session owns them (spec §9).

The graph state itself lives in the checkpointer; this store only remembers
who may touch a thread and whether it can still run. It is in memory on
purpose: the app runs one worker, and a restart forgetting every thread is
acceptable for a demo (the UI then starts a New chat).
"""
import uuid
from dataclasses import dataclass
from typing import Callable


@dataclass
class ThreadRecord:
    id: str
    session_id: str
    pattern_id: str
    mode: str
    closed: bool = False  # a run failed: the thread stays readable but never runs again
    ended: bool = False   # the graph finished normally (chat `stop`, or a trigger's one run)


class ThreadStore:
    def __init__(self) -> None:
        self._threads: dict[str, ThreadRecord] = {}
        self._active_runs: set[str] = set()  # session ids with a run in progress

    def create(self, session_id: str, pattern_id: str, mode: str) -> ThreadRecord:
        record = ThreadRecord(uuid.uuid4().hex, session_id, pattern_id, mode)
        self._threads[record.id] = record
        return record

    def get(self, thread_id: str, session_id: str) -> ThreadRecord:
        """Return the thread, or raise KeyError if it is unknown OR owned by
        another session. Callers turn both into the same 404, so a visitor
        can't probe which thread ids exist."""
        record = self._threads.get(thread_id)
        if record is None or record.session_id != session_id:
            raise KeyError(thread_id)
        return record

    def begin_run(self, session_id: str) -> bool:
        """Claim the session's single run slot; False if a run is already active."""
        if session_id in self._active_runs:
            return False
        self._active_runs.add(session_id)
        return True

    def end_run(self, session_id: str) -> None:
        """Release the run slot. Safe to call more than once."""
        self._active_runs.discard(session_id)


def once(fn: Callable[[], None]) -> Callable[[], None]:
    """Wrap ``fn`` so that only the first call runs it.

    The run slot is keyed by session, not by run, so a response that released
    its slot and then released it again could free the NEXT run's slot. Each
    response therefore gets one once-only release.
    """
    done = False

    def wrapper() -> None:
        nonlocal done
        if not done:
            done = True
            fn()

    return wrapper
