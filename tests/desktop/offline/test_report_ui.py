"""Headless report admission, cancellation and durable completion contracts."""
from types import SimpleNamespace
from pathlib import Path
import os
import subprocess
import sys

from desktop.offline.models import AuditFilter, OfflineError
from desktop.offline.report_ui import ReportController, choose_export
from desktop.offline.reporting import ReportResult


class Worker:
    def __init__(self):
        self.accept = True
        self.work = self.done = None

    def submit(self, work, done, key=None, write=False):
        assert write, 'File job completion must survive invalidated read generations.'
        self.work, self.done = work, done
        return self.accept


def app():
    notices = []
    return SimpleNamespace(worker=Worker(), closing=False, mutation_pending=False,
                           notices=notices, _notice=lambda *args: notices.append(args))


def test_durable_job_retains_result_and_late_cancel_cannot_undo_save():
    root = app()
    job = ReportController(root)
    assert job.start(AuditFilter(), Path('new.xlsx')) and job.pending
    assert not job.start(AuditFilter(), Path('second.xlsx'))
    job.cancel()
    result = ReportResult(Path('new.xlsx'), 0)
    root.worker.done(result, None)
    assert not job.pending and job.result == result
    assert '0' in job.message and 'saved' in job.message.lower()
    job.cancel()
    assert job.result == result


def test_queue_rejection_and_closing_are_truthful_and_retriable():
    root = app()
    job = ReportController(root)
    root.worker.accept = False
    assert not job.start(AuditFilter(), Path('new.xlsx'))
    assert not job.pending and job.result is None
    root.worker.accept = True
    assert job.start(AuditFilter(), Path('retry.xlsx'))
    root.worker.done(None, OfflineError('cancelled', 'Cancelled before save.'))
    assert not job.pending and job.result is None
    root.closing = True
    assert not job.start(AuditFilter(), Path('closed.xlsx'))


def test_report_refuses_competing_file_job_or_local_save():
    root = app()
    root.file_job = SimpleNamespace(pending=True)
    job = ReportController(root)
    assert not job.start(AuditFilter(), Path('busy.xlsx'))
    root.file_job.pending = False
    root.mutation_pending = True
    assert not job.start(AuditFilter(), Path('busy.xlsx'))


def test_pending_filter_edits_require_apply_before_destination_dialog():
    root = app()
    view = SimpleNamespace(app=root, applied_filters=('applied',), filter_state=lambda: ('edited',))
    def forbidden(**kwargs):
        raise AssertionError('Destination dialog must not open for unapplied edits.')
    assert not choose_export(view, choose_path=forbidden)
    assert 'apply' in root.notices[-1][0].lower()


def test_headless_controller_does_not_import_tk_or_online_client():
    script = '''
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'tkinter','customtkinter','_tkinter'} or fullname in {'desktop.api','desktop.reports'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from desktop.offline.report_ui import ReportController
'''
    completed = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                               cwd=Path(__file__).resolve().parents[3], env=dict(os.environ))
    assert completed.returncode == 0, completed.stderr


def test_real_worker_completion_survives_navigation_invalidation(tmp_path):
    from desktop.offline.repository import SqliteRepository
    from desktop.offline.worker import DatabaseWorker
    root = app()
    root.worker = DatabaseWorker(lambda: SqliteRepository(tmp_path / 'fictional.db'))
    job = ReportController(root)
    try:
        assert job.start(AuditFilter(), tmp_path / 'navigated.xlsx')
        root.worker.invalidate_reads()
        root.worker.close()
        root.worker.join(5)
        assert root.worker.stopped.is_set()
        root.worker.drain()
        assert not job.pending and job.result.count == 0
        assert job.result.path.is_file()
        assert 'saved' in root.notices[-1][0].lower()
    finally:
        root.worker.close()
        root.worker.join(5)


def test_coalesced_progress_never_overwrites_cancellation_or_completion():
    root = app()
    root.screen = SimpleNamespace(render_export=lambda: None)
    job = ReportController(root)
    assert job.start(AuditFilter(), Path('new.xlsx'))
    job._progress.post((100, 'Writing workbook'))
    job._progress.post((200, 'Writing workbook'))
    job.poll()
    assert '200' in job.message
    job.cancel()
    job._progress.post((300, 'Writing workbook'))
    job.poll()
    assert 'Cancellation' in job.message
    root.worker.done(ReportResult(Path('new.xlsx'), 300), None)
    job._progress.post((200, 'Writing workbook'))
    job.poll()
    assert 'saved' in job.message.lower() and '300' in job.message


def test_active_report_prevents_transfer_file_job_admission_on_real_worker(tmp_path):
    from types import MethodType
    from desktop.offline.lifecycle import OfflineLifecycle
    from desktop.offline.repository import SqliteRepository
    from desktop.offline.transfer_controller import TransferController
    from desktop.offline.worker import DatabaseWorker
    root = app()
    root.mutate = MethodType(OfflineLifecycle.mutate, root)
    root.worker = DatabaseWorker(lambda: SqliteRepository(tmp_path / 'fictional.db'))
    report = ReportController(root)
    messages = []
    view = SimpleNamespace(status=lambda *args, **kwargs: messages.append(args),
                           export_finished=lambda result: None)
    transfer = TransferController(root, view)
    try:
        assert report.start(AuditFilter(), tmp_path / 'report.xlsx')
        assert not transfer.publish(b'fictional', tmp_path / 'second.bhlitransfer')
        assert not transfer.pending
        assert not (tmp_path / 'second.bhlitransfer').exists()
        root.worker.close()
        root.worker.join(5)
        root.worker.drain()
        assert report.result.path.is_file()
    finally:
        root.worker.close()
        root.worker.join(5)
        root.worker.drain()
