"""Deterministic contracts for the durable, GUI-independent database worker."""

import importlib
import threading

import pytest


class Repository:
    def __init__(self):
        self.owner = threading.get_ident()
        self.calls = []
        self.closed = 0

    def record(self, value):
        assert threading.get_ident() == self.owner
        self.calls.append(value)
        return value

    def close(self):
        assert threading.get_ident() == self.owner
        self.closed += 1


@pytest.fixture
def workers():
    created = []
    releases = []

    def make(factory=Repository, capacity=32):
        worker = importlib.import_module("desktop.offline.worker").DatabaseWorker(
            factory, capacity=capacity
        )
        created.append(worker)
        return worker

    make.releases = releases
    yield make
    for event in releases:
        event.set()
    for worker in created:
        worker.close()
        worker.join(3)
        assert worker.stopped.is_set(), "database worker did not stop"


def blocking_write(workers, worker):
    entered, release = threading.Event(), threading.Event()
    workers.releases.append(release)

    def work(repo):
        entered.set()
        assert release.wait(3), "test did not release admitted write"
        return repo.record("committed")

    assert worker.submit(work, lambda result, error: None, write=True)
    assert entered.wait(3), "database worker did not begin write"
    return release


def stop(worker):
    worker.close()
    worker.join(3)
    assert worker.stopped.is_set()


def test_factory_operations_and_close_share_non_daemon_owner_thread(workers):
    repositories = []
    threads = []

    def factory():
        threads.append(threading.current_thread())
        repositories.append(Repository())
        return repositories[-1]

    worker = workers(factory)
    callbacks = []
    assert worker.submit(
        lambda repo: repo.record("profile"),
        lambda result, error: callbacks.append((threading.get_ident(), result, error)),
    )
    stop(worker)
    assert callbacks == []
    worker.drain()
    assert callbacks == [(threading.get_ident(), "profile", None)]
    assert repositories[0].owner != threading.get_ident()
    assert not threads[0].daemon
    assert repositories[0].closed == 1
    worker.close()
    assert repositories[0].closed == 1


def test_close_returns_with_blocked_write_then_preserves_fifo_and_rejects_work(workers):
    repo = []

    def factory():
        repo.append(Repository())
        return repo[0]

    worker = workers(factory, capacity=1)
    release = blocking_write(workers, worker)
    callbacks = []
    assert worker.submit(lambda r: r.record("second"), lambda *v: callbacks.append(v), write=True)
    worker.close()
    assert not worker.stopped.is_set()
    assert not worker.submit(lambda r: r.record("rejected"), lambda *v: callbacks.append(v))
    release.set()
    worker.join(3)
    assert worker.stopped.is_set()
    worker.drain()
    assert repo[0].calls == ["committed", "second"]
    assert callbacks == [("second", None)]
    assert repo[0].closed == 1


def test_full_queue_rejects_submission_without_orphan_callback(workers):
    worker = workers(capacity=1)
    release = blocking_write(workers, worker)
    callbacks = []
    assert worker.submit(lambda r: "queued", lambda *v: callbacks.append(v), write=True)
    assert not worker.submit(lambda r: "overflow", lambda *v: callbacks.append(v), write=True)
    release.set()
    stop(worker)
    worker.drain()
    assert callbacks == [("queued", None)]


def test_superseded_reads_do_not_run_or_deliver_but_same_key_writes_survive(workers):
    worker = workers()
    release = blocking_write(workers, worker)
    calls, callbacks = [], []

    def work(value):
        return lambda repo: calls.append(value) or value

    assert worker.submit(work("old"), lambda *v: callbacks.append(v), key="list")
    assert worker.submit(work("new"), lambda *v: callbacks.append(v), key="list")
    assert worker.submit(work("write1"), lambda *v: callbacks.append(v), key="list", write=True)
    assert worker.submit(work("write2"), lambda *v: callbacks.append(v), key="list", write=True)
    release.set()
    stop(worker)
    worker.drain()
    assert calls == ["new", "write1", "write2"]
    assert callbacks == [("new", None), ("write1", None), ("write2", None)]


def test_invalidation_drops_pending_reads_but_preserves_accepted_writes(workers):
    worker = workers()
    release = blocking_write(workers, worker)
    calls, callbacks = [], []
    assert worker.submit(lambda r: calls.append("old"), lambda *v: callbacks.append(v))
    assert worker.submit(lambda r: calls.append("write") or "write", lambda *v: callbacks.append(v), write=True)
    worker.invalidate_reads()
    assert worker.submit(lambda r: calls.append("fresh") or "fresh", lambda *v: callbacks.append(v))
    release.set()
    stop(worker)
    worker.drain()
    assert calls == ["write", "fresh"]
    assert callbacks == [("write", None), ("fresh", None)]


def test_finished_reads_can_be_invalidated_before_ui_drain(workers):
    worker = workers()
    callbacks = []
    assert worker.submit(lambda r: "stale", lambda *v: callbacks.append(v), key="list")
    stop(worker)
    worker.invalidate_reads()
    worker.drain()
    assert callbacks == []


def test_callback_failure_does_not_orphan_later_completions(workers):
    worker = workers()
    callbacks = []

    def failing_callback(*args):
        raise RuntimeError("UI callback failure")

    assert worker.submit(lambda r: "first", failing_callback, write=True)
    assert worker.submit(lambda r: "second", lambda *v: callbacks.append(v), write=True)
    stop(worker)
    with pytest.raises(RuntimeError, match="UI callback failure"):
        worker.drain()
    assert callbacks == [("second", None)]
    worker.drain()
    assert callbacks == [("second", None)]


def test_ui_lifecycle_methods_reject_another_thread(workers):
    worker = workers()
    errors = []

    def other_thread():
        for method in (worker.drain, worker.invalidate_reads, worker.close):
            try:
                method()
            except RuntimeError as error:
                errors.append(error)

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join(3)
    assert len(errors) == 3
    assert worker.submit(lambda r: "still open", lambda *v: None)


def test_capacity_must_be_a_positive_integer():
    cls = importlib.import_module("desktop.offline.worker").DatabaseWorker
    for capacity in (0, -1, True, 1.5):
        with pytest.raises((ValueError, TypeError)):
            cls(Repository, capacity=capacity)


def test_startup_failure_is_sanitized_for_each_accepted_request(workers):
    def factory():
        raise OSError("C:/private/customer.sqlite secret")

    worker = workers(factory)
    callbacks = []
    assert worker.submit(lambda repo: pytest.fail("factory failed"), lambda *v: callbacks.append(v))
    assert worker.submit(lambda repo: pytest.fail("factory failed"), lambda *v: callbacks.append(v), write=True)
    stop(worker)
    worker.drain()
    error_type = importlib.import_module("desktop.offline.models").OfflineError
    assert len(callbacks) == 2
    for result, error in callbacks:
        assert result is None
        assert isinstance(error, error_type)
        assert error.code == "storage"
        assert "private" not in str(error)
        assert error.__traceback__ is None


def test_repository_errors_preserve_code_and_unknown_errors_do_not_stop_writes(workers):
    error_type = importlib.import_module("desktop.offline.models").OfflineError
    worker = workers()
    callbacks = []

    def typed_error(repo):
        raise error_type("busy", "The local database is busy.")

    def private_error(repo):
        raise ValueError("secret customer path")

    assert worker.submit(typed_error, lambda *v: callbacks.append(v), write=True)
    assert worker.submit(private_error, lambda *v: callbacks.append(v), write=True)
    worker.invalidate_reads()
    assert worker.submit(lambda repo: repo.record("after errors"), lambda *v: callbacks.append(v), write=True)
    stop(worker)
    worker.drain()
    assert [error.code if error else None for _, error in callbacks] == ["busy", "storage", None]
    assert callbacks[-1] == ("after errors", None)
    assert "secret" not in str(callbacks[1][1])
    assert all(error.__traceback__ is None for _, error in callbacks if error)


def test_stopped_waits_for_close_and_close_failure_surfaces_once(workers):
    closing, release = threading.Event(), threading.Event()
    workers.releases.append(release)

    class CloseFailure(Repository):
        def close(self):
            super().close()
            closing.set()
            assert release.wait(3)
            raise OSError("private close path")

    worker = workers(CloseFailure)
    worker.close()
    assert closing.wait(3)
    assert not worker.stopped.is_set()
    release.set()
    worker.join(3)
    assert worker.stopped.is_set()
    error_type = importlib.import_module("desktop.offline.models").OfflineError
    assert isinstance(worker.close_error, error_type)
    assert worker.close_error.code == "storage"
    assert "private" not in str(worker.close_error)
    with pytest.raises(error_type):
        worker.drain()
    worker.drain()


def test_discarded_read_callback_is_released_on_creator_thread(workers):
    destroyed = []

    class Callback:
        def __call__(self, *args):
            pytest.fail("invalidated callback invoked")

        def __del__(self):
            destroyed.append(threading.get_ident())

    worker = workers()
    release = blocking_write(workers, worker)
    assert worker.submit(lambda repo: "old", Callback(), key="list")
    worker.invalidate_reads()
    assert destroyed == [threading.get_ident()]
    release.set()
    stop(worker)
    worker.drain()


def test_supersession_releases_callback_on_ui_without_discarding_write(workers):
    destroyed = []

    class Callback:
        def __call__(self, *args):
            pass

        def __del__(self):
            destroyed.append(threading.get_ident())

    worker = workers()
    release = blocking_write(workers, worker)
    assert worker.submit(lambda repo: "old", Callback(), key="list")
    assert worker.submit(lambda repo: "new", lambda *args: None, key="list")
    assert destroyed == [threading.get_ident()]
    release.set()
    stop(worker)
    worker.drain()


def test_startup_error_results_are_independent_even_if_a_callback_raises_one(workers):
    error_type = importlib.import_module("desktop.offline.models").OfflineError
    failed = threading.Event()

    def factory():
        failed.set()
        raise error_type("schema", "The local schema is not supported.")

    worker = workers(factory)
    assert failed.wait(3)
    errors = []

    def raising_callback(result, error):
        errors.append(error)
        raise error

    assert worker.submit(lambda r: None, raising_callback)
    assert worker.submit(lambda r: None, lambda result, error: errors.append(error))
    stop(worker)
    with pytest.raises(error_type):
        worker.drain()
    assert len(errors) == 2
    assert errors[0].code == errors[1].code == "schema"
    assert errors[0] is not errors[1]
    assert errors[1].__traceback__ is None


def test_real_repository_rolls_back_failed_write_then_commits_before_close(workers, tmp_path):
    from desktop.offline.models import AuditFilter, new_uuid
    from desktop.offline.repository import SqliteRepository

    path = tmp_path / "worker.sqlite"
    worker = workers(lambda: SqliteRepository(path))
    failed_id, committed_id = new_uuid(), new_uuid()
    values = dict(driver_name="Fictional Driver", helper_name=None,
                  audit_date="2026-11-05", station="Fictional Station",
                  plate_number="TEST-6C", remarks=None)
    callbacks = []

    def failed_write(repo):
        repo._connection.execute(
            "CREATE TRIGGER fail_event BEFORE INSERT ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'private storage failure'); END"
        )
        return repo.create(failed_id, values)

    entered, release = threading.Event(), threading.Event()
    workers.releases.append(release)

    def committed_write(repo):
        repo._connection.execute("DROP TRIGGER fail_event")
        entered.set()
        assert release.wait(3)
        return repo.create(committed_id, values)

    assert worker.submit(lambda r: r.save_profile("Fictional Auditor"), lambda *v: callbacks.append(v), write=True)
    assert worker.submit(failed_write, lambda *v: callbacks.append(v), write=True)
    assert worker.submit(committed_write, lambda *v: callbacks.append(v), write=True)
    assert entered.wait(3)
    worker.invalidate_reads()
    worker.close()
    assert not worker.stopped.is_set()
    release.set()
    worker.join(3)
    assert worker.stopped.is_set()
    worker.drain()
    assert callbacks[0][1] is None
    assert callbacks[1][0] is None and callbacks[1][1].code == "storage"
    assert "private" not in str(callbacks[1][1])
    assert callbacks[2][0].id == committed_id and callbacks[2][1] is None
    repo = SqliteRepository(path)
    try:
        assert [item.id for item in repo.list(AuditFilter()).items] == [committed_id]
        assert repo.history(committed_id).total == 1
        assert repo._connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 1
    finally:
        repo.close()
