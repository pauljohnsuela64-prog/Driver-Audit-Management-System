"""Offline composition: one local database worker and the existing desktop UI."""
from dataclasses import replace
from datetime import date
from pathlib import Path
import tkinter as tk

import customtkinter as ctk

from desktop.components.common import StatePanel, button, destroy_view
from desktop.lifecycle import UiCollector
from desktop.models import AuditQuery
from desktop.offline.models import LocalPage, OfflineError
from desktop.offline.presentation import OfflineDraft, FIELDS, local_filter, present_audit, record_values
from desktop.offline.repository import SqliteRepository
from desktop.offline.worker import DatabaseWorker
from desktop.screens.shell import Shell
from desktop.theme import color


def _repository(path):
    """Executed only by the database thread, including connection creation."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise OfflineError('storage', 'The local data folder is unavailable. Check access and retry.') from None
    return SqliteRepository(path)


class OfflineApplication(ctk.CTk):
    offline = True
    destinations = ('Dashboard', 'Driver Audits', 'Local profile')

    def __init__(self, db_path=None, worker_factory=None):
        self.collector = UiCollector()
        self.worker = None
        try:
            super().__init__()
            self.tk.call('auto_load', 'tk_focusNext')
            self.tk.call('auto_load', 'tk_focusPrev')
            if db_path is None:
                from desktop.offline.identity import database_path
                db_path = database_path()
            self.db_path = Path(db_path)
            self._worker_factory = worker_factory or DatabaseWorker
            self.profile = None
            self.query = AuditQuery()
            self.selected_id = None
            self.draft = None
            self.dialog = None
            self.shell = None
            self.screen = None
            self.destination = ''
            self.mutation_pending = False
            self.closing = self.closed = False
            self._generation = 0
            self._retry_bootstrap = False
            self._poll_timer = None
            self._close_warning = False
            self._shutdown_write_error = None
            self.title('BHLI Audit Offline')
            from desktop.resources import resource_path
            icon = resource_path('bhli.ico')
            if icon.exists():
                self.iconbitmap(default=str(icon))
            scale = self._get_window_scaling()
            width = min(1280, int(self.winfo_screenwidth() / scale) - 40)
            height = min(800, int(self.winfo_screenheight() / scale) - 80)
            self.geometry(f'{width}x{height}')
            self.minsize(min(800, width), min(600, height))
            self.configure(fg_color=color('bg'))
            self.protocol('WM_DELETE_WINDOW', self.close)
            self.bind('<Escape>', self.escape)
            self.bind('<F5>', lambda event: self.refresh())
            self.bind('<Control-f>', lambda event: self.focus_search())
            self._start_worker()
            self._poll_timer = self.after(30, self.poll)
        except BaseException:
            if self.worker is not None:
                self.worker.close()
                self.worker.join()
            if hasattr(self, 'tk'):
                destroy_view(self)
            self.collector.close()
            raise

    def _start_worker(self):
        if self.worker is not None and not self.worker.stopped.is_set():
            return
        self._retry_bootstrap = False
        self._replace_root_view(StatePanel(self, 'Opening local audit storage', 'Records remain on this computer.'))
        path = self.db_path
        self.worker = self._worker_factory(lambda: _repository(path))
        self.worker.submit(lambda repo: repo.profile(), self._bootstrapped, key='bootstrap')

    def _bootstrapped(self, profile, error):
        if self.closing:
            return
        if error:
            self.worker.close()
            self._replace_root_view(StatePanel(self, 'Local storage unavailable',
                str(error) + ' Your existing database has not been replaced. Retry after resolving the problem.',
                self.retry_bootstrap))
            return
        self.profile = profile
        if profile is None:
            from desktop.offline.views import ProfileView
            self.destination = 'Local profile'
            self._replace_root_view(ProfileView(self, self))
        else:
            self.rebuild_shell('Dashboard')

    def retry_bootstrap(self):
        if self.closing or self.mutation_pending:
            return
        if self.worker.stopped.is_set():
            self._start_worker()
        else:
            self._retry_bootstrap = True

    def _replace_root_view(self, view):
        if self.screen is not None and self.screen.winfo_exists():
            destroy_view(self.screen)
        self.screen = view
        view.pack(fill='both', expand=True, padx=24, pady=24)

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

    def report_callback_exception(self, exc, value, traceback):
        self._notice('The interface could not complete this action. Your local data was not reset. Try Refresh.')

    def _notice(self, message, error=True):
        if self.closed:
            return
        target = self.shell.notice if self.shell else getattr(self.screen, 'notice', None)
        if target is not None:
            target.show(message, error)

    def request(self, work, done, key='screen'):
        if self.closing:
            return False
        generation = self._generation
        owner = getattr(done, '__self__', None)
        def completed(result, error):
            if self.closing or generation != self._generation:
                return
            if isinstance(owner, tk.Misc):
                try:
                    if not owner.winfo_exists():
                        return
                except tk.TclError:
                    return
            done(result, error)
        accepted = self.worker.submit(work, completed, key=key)
        if not accepted:
            completed(None, OfflineError('queue', 'Local storage is busy. No new operation was queued. Retry.'))
        return accepted

    def read_audits(self, query, done):
        query_filter = local_filter(query)
        def completed(page, error):
            if not error:
                page = LocalPage(tuple(present_audit(item) for item in page.items), page.total, page.page, page.page_size)
            done(page, error)
        return self.request(lambda repo: repo.list(query_filter), completed)

    def read_audit(self, identity, done):
        return self.request(lambda repo: repo.read(identity),
                            lambda record, error: done(present_audit(record) if record is not None else None, error))

    def read_history(self, identity, page, done):
        return self.request(lambda repo: repo.history(identity, page=page), done)

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

    def rebuild_shell(self, destination=None, audit_id=None):
        self.worker.invalidate_reads()
        self._generation += 1
        if self.shell is not None:
            destroy_view(self.shell)
        elif self.screen is not None:
            destroy_view(self.screen)
        self.screen = None
        self.shell = Shell(self, self, local_profile=self.profile, destinations=self.destinations)
        self.shell.pack(fill='both', expand=True)
        self.shell.footer.configure(text='Offline · Development edition\nFictional data only · No backup yet')
        self.navigate(destination or 'Dashboard', audit_id, force=True)

    def navigate(self, destination, audit_id=None, force=False):
        if self.closing or self.profile is None or self.shell is None:
            return
        if self.mutation_pending:
            self._notice('Wait for the local save to finish before navigating.', False)
            return
        if not force and not self.leave_form(lambda: self.navigate(destination, audit_id, force=True)):
            return
        if destination not in (*self.destinations, 'Audit Details', 'Audit History', 'Create Audit', 'Edit Audit'):
            return
        self.worker.invalidate_reads()
        self._generation += 1
        if self.screen is not None:
            destroy_view(self.screen)
        self.screen = None
        self.destination = destination
        self.shell.select(destination)
        if destination == 'Dashboard':
            from desktop.screens.dashboard import Dashboard
            screen = Dashboard(self.shell.content, self)
        elif destination == 'Driver Audits':
            from desktop.screens.audits import Audits
            screen = Audits(self.shell.content, self)
        elif destination == 'Audit Details':
            from desktop.screens.details import Details
            screen = Details(self.shell.content, self, audit_id)
        elif destination == 'Audit History':
            from desktop.screens.audit_history import AuditHistory
            screen = AuditHistory(self.shell.content, self, audit_id)
        elif destination in ('Create Audit', 'Edit Audit') and self.draft is not None:
            from desktop.offline.forms import OfflineAuditForm
            screen = OfflineAuditForm(self.shell.content, self, self.draft)
        else:
            from desktop.offline.views import ProfileView
            screen = ProfileView(self.shell.content, self)
        self.screen = screen
        screen.pack(fill='both', expand=True)
        target = getattr(screen, 'search', screen)
        target.focus_set()

    def leave_form(self, accepted):
        if self.mutation_pending:
            self._notice('Wait for the local save to finish before navigating.', False)
            return False
        if self.draft:
            if hasattr(self.screen, 'capture'):
                self.screen.capture()
            if self.draft.dirty:
                from desktop.components.audit_dialogs import confirm
                uncertain = self.draft.uncertain
                def discard():
                    self.draft = None
                    if uncertain:
                        # A committed-but-unconfirmed creation may exist. Show an actual
                        # refreshed list before the employee starts another operation.
                        self.query = replace(self.query, page=1)
                        self.navigate('Driver Audits', force=True)
                        self._notice('Draft discarded. Inspect the refreshed local records for the previous save.', False)
                    else:
                        accepted()
                confirm(self, 'Leave this audit?',
                        ('The previous save may already exist. Discarding loses its safe retry identity. '
                         'The local records will be refreshed for inspection. ' if uncertain else '') +
                        'Unsaved form data will be discarded.', discard, 'Discard draft')
                return False
            self.draft = None
        return True

    def open_create(self):
        if self.closing or self.profile is None:
            return
        def opened():
            self.draft = OfflineDraft({key: date.today().isoformat() if key == 'audit_date' else '' for key in FIELDS})
            self.navigate('Create Audit', force=True)
        if self.leave_form(opened):
            opened()

    def open_edit(self, record):
        if self.closing or record.deleted_at:
            return
        def load():
            def loaded(latest, error):
                if error:
                    self._notice(str(error))
                elif latest.deleted_at:
                    self._notice('This audit is archived and read-only. Refresh to view its current state.')
                else:
                    self.draft = OfflineDraft(record_values(latest), baseline=latest)
                    self.navigate('Edit Audit', force=True)
            self.read_audit(record.id, loaded)
        if self.leave_form(load):
            load()

    def render_draft(self):
        if not self.closing and self.draft is not None and getattr(self.screen, 'draft', None) is self.draft:
            self.screen.render_state()

    def rebuild_form(self):
        self.navigate('Edit Audit' if self.draft.baseline else 'Create Audit', force=True)

    def saved(self, identity):
        self.query = replace(self.query, page=1)
        self.selected_id = identity
        self.navigate('Driver Audits', force=True)
        self._notice('Audit saved locally. Filters are preserved. If the list cannot refresh, use Refresh; the save is confirmed.', False)

    def confirm_archive(self, record):
        if self.closing or self.mutation_pending or self.dialog is not None:
            return
        def loaded(latest, error):
            if error:
                self._notice(str(error))
                return
            if latest.deleted_at:
                self._notice('This audit is already archived. Refresh to view its current state.', False)
                return
            from desktop.components.audit_dialogs import confirm
            identity, revision = latest.id, latest.revision
            def archive():
                def completed(result, failure):
                    if self.closing:
                        return
                    if failure:
                        self._notice(str(failure) + ' Refresh and confirm again before archiving. No automatic retry was made.')
                        return
                    self.query = replace(self.query, page=1)
                    self.selected_id = None
                    self.navigate('Driver Audits', force=True)
                    self._notice('Audit archived locally. Its history is preserved.', False)
                self.mutate(lambda repo: repo.archive(identity, revision), completed)
            confirm(self, 'Archive this audit?',
                    f'{latest.driver_name}\n{latest.plate_number} · {latest.station}\n{latest.audit_date}\n'
                    'Archiving makes this audit read-only and preserves its history.',
                    archive, 'Archive audit', destructive=True)
        self.read_audit(record.id, loaded)

    def render_history_event(self, parent, event):
        from desktop.offline.views import render_history_event
        render_history_event(parent, event)

    def set_theme(self, appearance):
        if self.closing or self.mutation_pending or self.dialog is not None:
            self._notice('Wait for the current operation or close the dialog before changing appearance.', False)
            return
        self.focus_set()
        if hasattr(self.screen, 'capture'):
            self.screen.capture()
        ctk.set_appearance_mode(appearance)
        if self.profile is not None:
            self.rebuild_shell(self.destination, getattr(self.screen, 'audit_id', None))

    def refresh(self):
        if not self.closing and not self.mutation_pending and hasattr(self.screen, 'refresh'):
            self.screen.refresh()

    def focus_search(self):
        if not self.closing and hasattr(self.screen, 'search'):
            self.screen.search.focus_set()
            return 'break'

    def escape(self, event=None):
        if self.closing or self.dialog is not None:
            return
        if self.shell and self.shell.menu.winfo_ismapped():
            self.shell.hide_menu()
        elif self.destination in ('Audit Details', 'Audit History', 'Create Audit', 'Edit Audit'):
            self.navigate('Driver Audits')

    def close(self, force=False):
        if self.closed or self.closing:
            return
        if not self.mutation_pending and not force and not self.leave_form(lambda: self.close(force=True)):
            return
        if self.dialog is not None:
            self.dialog.dismiss()
        self.closing = True
        self.worker.invalidate_reads()
        self._generation += 1
        self.worker.close()
        self._notice('Closing… Waiting for all submitted local saves and database shutdown. Please keep this window open.', False)
        if self.shell is None:
            self._replace_root_view(StatePanel(self, 'Closing local storage', 'Waiting for submitted operations to finish…'))
        if self.worker.stopped.is_set():
            self._finish_close()

    def _show_close_error(self, error):
        if self._close_warning:
            return
        self._close_warning = True
        if self.shell is not None:
            destroy_view(self.shell)
            self.shell = self.screen = None
        message = str(error)
        if self._shutdown_write_error is not None and error is not self._shutdown_write_error:
            message += '\n' + str(self._shutdown_write_error)
        panel = StatePanel(self, 'Local storage needs attention',
            message + ' The database was not replaced. Keep its file for inspection.')
        button(panel, 'Close application', self._finish_close).pack(pady=(0, 24))
        self._replace_root_view(panel)

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
        destroy_view(self)
        self.screen = self.shell = self.dialog = None
        self.draft = None
        self.collector.close()
