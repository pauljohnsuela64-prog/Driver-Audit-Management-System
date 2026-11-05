"""One durable repository thread with creator-thread completion delivery.

Work functions must capture database inputs only; GUI callbacks belong in ``done``.
Closing stops admission immediately and lets every accepted write finish. The UI
must keep draining until ``stopped`` is set, drain once more, then destroy widgets.
Read invalidation suppresses presentation; it cannot roll back a running operation.
"""

from collections import deque
from dataclasses import dataclass
from queue import Empty, SimpleQueue
import threading
from typing import Any, Callable

from .models import OfflineError


@dataclass(frozen=True)
class _Request:
    number: int
    work: Callable[[Any], Any]
    key: Any
    generation: int
    write: bool


def _safe_error(error: Exception) -> OfflineError:
    # Reconstruct even typed errors: traceback/context can retain work closures,
    # database internals or private exception text across the thread boundary.
    if isinstance(error, OfflineError):
        return OfflineError(error.code, error.message)
    return OfflineError("storage", "The local database operation could not be completed.")


class DatabaseWorker:
    """Bounded FIFO admission; no GUI callbacks are passed to the worker queue.

    All public methods except ``join`` belong to the constructing/UI thread.
    ``capacity`` bounds waiting work, excluding the currently running operation.
    The shutdown marker has a reserved control slot and never waits for capacity.
    Repository operations own their transaction/rollback behavior.
    """

    def __init__(self, factory: Callable[[], Any], capacity: int = 32):
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError("capacity must be a positive integer")
        if capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self._owner = threading.get_ident()
        self._capacity = capacity
        self._condition = threading.Condition()
        self._pending = deque()
        self._results = SimpleQueue()
        self._accepting = True
        self._generation = 0
        self._next_number = 0
        self._latest = {}
        # Only creator-thread methods read, invoke or remove these callbacks.
        self._callbacks = {}
        self.close_error = None
        self._close_error_delivered = False
        self.stopped = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(factory,), name="offline-database", daemon=False
        )
        self._thread.start()

    def _assert_owner(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError("Database worker UI methods require their creator thread.")

    def submit(self, work, done, key=None, write=False) -> bool:
        """Accept a repository operation without blocking; false means not queued."""
        self._assert_owner()
        with self._condition:
            if not self._accepting or len(self._pending) >= self._capacity:
                return False
            number = self._next_number
            self._next_number += 1
            request = _Request(number, work, key, self._generation, bool(write))
            if not write and key is not None:
                previous = self._latest.get(key)
                self._latest[key] = number
                # Removing on UI thread releases Tk-owned callback references here.
                self._callbacks.pop(previous, None)
            self._callbacks[number] = (done, request.generation, bool(write), key)
            self._pending.append(request)
            self._condition.notify()
        return True

    def _current(self, request):
        # Called under the condition lock; writes are never superseded.
        return request.write or (
            request.generation == self._generation
            and (request.key is None or self._latest.get(request.key) == request.number)
        )

    def invalidate_reads(self):
        """Forget read callbacks/queued reads, retaining all admitted mutations."""
        self._assert_owner()
        with self._condition:
            self._generation += 1
            self._latest.clear()
            for number, (_, _, write, _) in list(self._callbacks.items()):
                if not write:
                    del self._callbacks[number]

    def drain(self):
        """Deliver available results on the UI thread, then surface first failure.

        A failing callback does not prevent later completions from being handled.
        Close failures surface once here and remain inspectable in ``close_error``.
        """
        self._assert_owner()
        callback_error = None
        while True:
            try:
                number, result, error = self._results.get_nowait()
            except Empty:
                break
            registered = self._callbacks.pop(number, None)
            if registered is None:
                continue
            done, generation, write, key = registered
            if not write and (
                generation != self._generation
                or (key is not None and self._latest.get(key) != number)
            ):
                continue
            if not write and key is not None:
                with self._condition:
                    if self._latest.get(key) == number:
                        del self._latest[key]
            try:
                done(result, error)
            except Exception as failure:
                if callback_error is None:
                    callback_error = failure
        if callback_error is not None:
            raise callback_error
        if self.stopped.is_set() and self.close_error is not None and not self._close_error_delivered:
            self._close_error_delivered = True
            raise self.close_error

    def close(self):
        """Stop admission and append a FIFO shutdown marker without waiting."""
        self._assert_owner()
        with self._condition:
            if self._accepting:
                self._accepting = False
                self._pending.append(None)
                self._condition.notify()

    def join(self, timeout=None):
        self._thread.join(timeout)

    def _run(self, factory):
        repository = None
        startup_error = None
        try:
            try:
                repository = factory()
            except Exception as error:
                startup_error = _safe_error(error)
            # Factory and work closures can hold resources. Drop them on this
            # owning thread; GUI callbacks are retained exclusively by the UI.
            factory = None
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: bool(self._pending))
                    request = self._pending.popleft()
                    if request is None:
                        break
                    current = self._current(request)
                if not current:
                    request = None
                    continue
                result = None
                # Each completion owns its error. A UI callback may raise or
                # annotate it without attaching a traceback to future results.
                failure = None if startup_error is None else _safe_error(startup_error)
                if startup_error is None:
                    try:
                        result = request.work(repository)
                    except Exception as error:
                        failure = _safe_error(error)
                self._results.put((request.number, result, failure))
                request = None
                result = failure = None
        finally:
            try:
                if repository is not None:
                    repository.close()
            except Exception as error:
                self.close_error = _safe_error(error)
            finally:
                repository = None
                self.stopped.set()
