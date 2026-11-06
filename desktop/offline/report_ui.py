"""Headless durable report jobs and lazy Tk destination selection.

Worker closures contain only immutable inputs and a coalescing progress handle.
Completion belongs to this application controller, never to a disposed screen.
"""
from threading import Event, Lock

from .models import OfflineError
from .reporting import export_report


class _Progress:
    def __init__(self):
        self.lock = Lock()
        self.latest = None

    def post(self, value):
        with self.lock:
            self.latest = value

    def take(self):
        with self.lock:
            latest, self.latest = self.latest, None
            return latest


class ReportController:
    def __init__(self, app):
        self.app = app
        self.pending = False
        self.result = None
        self.message = ''
        self.cancel_event = Event()
        self._progress = _Progress()

    def start(self, applied_filter, path):
        app = self.app
        if (self.pending or app.closing or app.mutation_pending or
                any(getattr(getattr(app, name, None), 'pending', False)
                    for name in ('file_job', 'backup_job'))):
            return False
        self.pending, self.result = True, None
        self.cancel_event = Event()
        self._progress = _Progress()
        app.file_job = self
        self.message = 'Preparing a point-in-time local snapshot. The report is unencrypted.'
        token, progress = self.cancel_event, self._progress
        def work(repo):
            return export_report(repo, applied_filter, path, cancel=token.is_set, progress=progress.post)
        def done(result, error):
            self.pending = False
            self._progress.take()
            self.result = result
            if error:
                self.message = str(error)
            else:
                self.message = f'Report saved: {result.path} ({result.count:,} records).'
                if result.cleanup_warning:
                    self.message += ' ' + result.cleanup_warning
            if not app.closing:
                app._notice(self.message, bool(error))
            elif ((error and getattr(error, 'code', None) != 'cancelled') or
                    (result and result.cleanup_warning)):
                previous = getattr(app, '_shutdown_write_error', None)
                app._shutdown_write_error = OfflineError('report_file',
                    (str(previous) + '\n' if previous else '') + self.message)
        # Durable admission is intentional even though snapshot SQL is read-only:
        # normal navigation invalidates reads and must not drop file completions.
        if not app.worker.submit(work, done, write=True):
            done(None, OfflineError('queue', 'Local storage is busy. No export was queued. Retry.'))
            return False
        return True

    def cancel(self):
        if self.pending:
            self.cancel_event.set()
            self.message = 'Cancellation requested. Waiting for the result; a completed save remains saved.'

    def poll(self):
        value = self._progress.take()
        if self.pending and value is not None and not self.cancel_event.is_set():
            self.message = f'{value[1]}: {value[0]:,} records. Unencrypted local report.'
        if not self.app.closing:
            render = getattr(getattr(self.app, 'screen', None), 'render_export', None)
            if render is not None:
                render()


def choose_export(view, *, choose_path=None):
    """Export the last applied list filters; unapplied form edits block selection."""
    app = view.app
    if view.filter_state() != view.applied_filters:
        app._notice('Apply or discard your pending filter edits before exporting. Clear all exports all audits.')
        return False
    if app.closing:
        return False
    job = app.report_job
    if job.pending or app.mutation_pending or getattr(getattr(app, 'backup_job', None), 'pending', False):
        app._notice('Wait for the current local file operation or save to finish.', False)
        return False
    if choose_path is None:
        from tkinter.filedialog import asksaveasfilename
        choose_path = asksaveasfilename
    path = choose_path(parent=app, title='Save unencrypted report of all matching audits (new filename)',
                       defaultextension='.xlsx', filetypes=[('Excel workbook', '*.xlsx')],
                       initialfile='BHLI-offline-audits.xlsx', confirmoverwrite=False)
    if not path:
        return False
    from .presentation import local_filter
    accepted = job.start(local_filter(app.query), path)
    if accepted:
        view.render_export()
    return accepted
