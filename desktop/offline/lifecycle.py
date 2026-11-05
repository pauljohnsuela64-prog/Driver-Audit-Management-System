"""Offline worker lifecycle contracts, independent of Tk."""
from desktop.offline.models import OfflineError


class OfflineLifecycle:
    def poll(self):
        self._poll_timer = None
        try:
            try:
                self.worker.drain()
            except OfflineError as error:
                if self.closing:
                    self._show_close_error(error)
                else:
                    self._notice(str(error))
            self.collector.poll()
            if self.closing and self.worker.stopped.is_set() and not self._close_warning:
                self._finish_close()
            elif self._retry_bootstrap and self.worker.stopped.is_set():
                self._start_worker()
        finally:
            if not self.closed:
                self._poll_timer = self.after(30, self.poll)

    def mutate(self, work, done):
        if self.closing or self.mutation_pending:
            done(None, OfflineError('queue', 'Wait for the submitted operation to finish. No new operation was queued.'))
            return False
        self.mutation_pending = True
        def completed(result, error):
            self.mutation_pending = False
            if self.closing and error:
                self._shutdown_write_error = OfflineError(error.code,
                    'A submitted local change was not confirmed. Reopen and inspect local records '
                    'before retrying. No automatic retry was made.')
            done(result, error)
        if not self.worker.submit(work, completed, write=True):
            self.mutation_pending = False
            done(None, OfflineError('queue', 'Local storage is busy. No new operation was queued. Retry.'))
            return False
        return True

    def _finish_close(self):
        if self.closed or not self.worker.stopped.is_set():
            return
        if not self._close_warning:
            # A final completion/error can arrive between poll's drain and its
            # stopped check. Release every callback on the UI thread first.
            try:
                self.worker.drain()
            except OfflineError as error:
                self._show_close_error(error)
                return
            if self.worker.close_error is not None:
                self._show_close_error(self.worker.close_error)
                return
            if self._shutdown_write_error is not None:
                self._show_close_error(self._shutdown_write_error)
                return
        self.closed = True
        if self._poll_timer is not None:
            self.after_cancel(self._poll_timer)
            self._poll_timer = None
        self._destroy_window()
        self.screen = self.shell = self.dialog = None
        self.draft = None
        self.collector.close()
