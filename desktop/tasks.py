"""Bounded daemon workers; callbacks run exclusively from caller's drain()."""
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Lock, Thread, get_ident

from desktop.api import ApiError


@dataclass(repr=False)
class Job:
    key: str
    serial: int
    work: object
    dispose: object


class Tasks:
    def __init__(self, workers=4, capacity=8):
        self.owner = get_ident()
        self._lock = Lock()
        self._queue = Queue()
        self._results = Queue()
        self._current = {}
        self._callbacks = {}
        self._serial = 0
        self._outstanding = 0
        self._capacity = capacity
        self._closed = False
        for _ in range(workers):
            Thread(target=self._worker, daemon=True, name='bhli-http').start()

    def submit(self, key, work, done, dispose=None):
        with self._lock:
            if self._closed or self._outstanding >= self._capacity:
                return False
            self._serial += 1
            self._current[key] = self._serial
            self._outstanding += 1
            self._callbacks[self._serial] = done
            self._queue.put(Job(key, self._serial, work, dispose))
        return True

    def _valid(self, job):
        with self._lock:
            return not self._closed and self._current.get(job.key) == job.serial

    @staticmethod
    def _dispose(job, result):
        if result is not None and job.dispose:
            try:
                job.dispose(result)
            except Exception:
                pass

    def _worker(self):
        while True:
            job = self._queue.get()
            if job is None:
                return
            result, error = None, None
            try:
                if not self._valid(job):
                    continue
                try:
                    result = job.work()
                except ApiError as exc:
                    error = exc
                except Exception:
                    error = ApiError(message='This request could not be completed. Please try again.')
                # Atomically enqueue or dispose, so close cannot miss an orphaned login.
                with self._lock:
                    valid = not self._closed and self._current.get(job.key) == job.serial
                    if valid:
                        self._results.put((job, result, error))
                if not valid:
                    self._dispose(job, result)
            finally:
                with self._lock:
                    self._outstanding -= 1

    def drain(self):
        if get_ident() != self.owner:
            raise RuntimeError('Only the UI thread may drain completions')
        while True:
            try:
                job, result, error = self._results.get_nowait()
            except Empty:
                break
            if self._valid(job):
                callback = self._callbacks.pop(job.serial, None)
                if callback:
                    callback(result, error)
            elif job.dispose and result is not None:
                # Disposal may call HTTP; never do that on the Tk thread.
                Thread(target=self._dispose, args=(job, result), daemon=True).start()
            self._callbacks.pop(job.serial, None)

    def invalidate(self):
        with self._lock:
            self._current.clear()
        self._callbacks.clear()
        self._discard_results()

    def _discard_results(self):
        while True:
            try:
                job, result, error = self._results.get_nowait()
            except Empty:
                return
            if result is not None and job.dispose:
                Thread(target=self._dispose, args=(job, result), daemon=True).start()

    def close(self):
        with self._lock:
            self._closed = True
            self._current.clear()
        self._callbacks.clear()
        self._discard_results()
        # Wake all idle workers, without waiting for pending network requests.
        for _ in range(4):
            self._queue.put(None)
