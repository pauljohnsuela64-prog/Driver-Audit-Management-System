"""Durable backup controller; Tk is imported only when opening the screen.

All storage objects stay on the repository owner. UI receives metadata and opaque
one-use handles only. Password references are consumed by worker closures.
"""
from dataclasses import dataclass
from threading import Event

from .models import OfflineError
from .report_ui import _Progress


def _owner(repo):
    if not hasattr(repo, '_backup_store'):
        from .backup_jobs import BackupJobs
        from .backup_store import BackupStore
        repo._backup_store = BackupStore(BackupJobs(repo, repo._path.parent / 'backup-recovery'))
    return repo._backup_store


def _summary(state):
    profile = state.rows['local_profile']
    return dict(profile=dict(profile[0]) if profile else None,
                installation=dict((row['key'], row['value']) for row in state.rows['app_meta']).get('installation_id'),
                counts={table: len(rows) for table, rows in state.rows.items()},
                metadata=dict(state.metadata))


@dataclass(frozen=True)
class Preview:
    id: str
    candidate: dict
    current: dict
    unchanged: bool


class BackupController:
    def __init__(self, app):
        self.app = app
        self.pending = self.blocked = False
        self.phase = 'idle'
        self.message = ''
        self.result = self.preview = self._ticket = None
        self.cancel_event = Event()
        self._progress = _Progress()

    def _admit(self):
        app = self.app
        return not (self.pending or self.blocked or app.closing or app.mutation_pending or
                    getattr(getattr(app, 'draft', None), 'dirty', False) or
                    any(getattr(getattr(app, name, None), 'pending', False)
                        for name in ('file_job', 'report_job')))

    def _password(self, password, confirmation=None):
        from .backup_crypto import _password
        try:
            raw = _password(password)
            if confirmation is not None and raw != _password(confirmation):
                raise OfflineError('backup_password', 'Passphrase confirmation must match exactly.')
            return True
        except OfflineError as error:
            self.message = str(error)
            return False

    def _submit(self, phase, operation, completed):
        self.phase, self.pending = phase, True
        self.app.file_job = self
        token, progress = self.cancel_event, self._progress
        def work(repo):
            return operation(_owner(repo), token.is_set, progress.post)
        def done(result, error):
            self._progress.take()
            self.result = result
            if error:
                self.phase, self.pending = 'error', False
                self.message = str(error)
            else:
                completed(result)
            if self.app.closing:
                if error and getattr(error, 'code', '') != 'cancelled' or getattr(result, 'cleanup_warning', ''):
                    previous = getattr(self.app, '_shutdown_write_error', None)
                    self.app._shutdown_write_error = OfflineError('backup_file',
                        (str(previous) + '\n' if previous else '') + self.message)
                if self.phase in ('preview', 'prepared'):
                    self.cancel()
            else:
                self.app._notice(self.message, bool(error) or self.blocked)
        if not self.app.worker.submit(work, done, write=True):
            done(None, OfflineError('queue', 'Storage is busy. No backup operation was queued.'))
            return False
        return True

    def create(self, password, confirmation, destination):
        if not self._admit() or not destination or not self._password(password, confirmation):
            return False
        self.cancel_event = Event()
        def operation(owner, cancel, progress):
            nonlocal password, confirmation
            confirmation = None
            try:
                artifact = owner.jobs.create(password, cancel=cancel, progress=progress)
                return owner.jobs.publish(artifact.id, destination, cancel=cancel)
            finally:
                password = None
        def saved(result):
            self.phase, self.pending = 'saved', False
            self.message = f'Complete encrypted backup saved and verified: {result.path}. ' + result.cleanup_warning
        accepted = self._submit('creating', operation, saved)
        if not accepted:
            password = confirmation = None
        return accepted

    def inspect(self, source, password):
        if not self._admit() or not source or not self._password(password):
            return False
        self.cancel_event = Event()
        self.preview = None
        def operation(owner, cancel, progress):
            nonlocal password
            try:
                value = owner.inspect_restore(source, password, cancel=cancel)
                return Preview(value.id, _summary(value.candidate), _summary(value.current), value.unchanged)
            finally:
                password = None
        def inspected(value):
            if self.cancel_event.is_set():
                self.preview = None
                self.phase, self.pending = 'cancelled', False
                self.message = 'Preview cancelled. No local data was replaced.'
                return
            self.preview = value
            self.phase, self.pending = ('unchanged', False) if value.unchanged else ('preview', True)
            self.message = ('This complete state is already present. Nothing needs replacement.' if value.unchanged else
                'Authenticated preview. Replacement includes every audit, history, receipt, profile and installation identity. Close other copies and older versions. Protect current data before confirming.')
        accepted = self._submit('inspecting', operation, inspected)
        if not accepted:
            password = None
        return accepted

    def prepare(self, password, recovery_destination):
        if self.app.closing or self.phase != 'preview' or not recovery_destination or not self._password(password):
            return False
        identifier = self.preview.id
        def operation(owner, cancel, progress):
            nonlocal password
            try:
                ticket = owner.prepare_restore(identifier, password, recovery_destination, cancel=cancel, progress=progress)
                if cancel():
                    owner.cancel_prepared(ticket)
                    raise OfflineError('cancelled', 'Preparation cancelled. Any saved recovery backup remains available.')
                return ticket
            finally:
                password = None
        def prepared(ticket):
            self._ticket = ticket
            self.phase, self.pending = 'prepared', True
            self.message = 'Current recovery backup saved and independently verified. Cancel is the default. Explicit confirmation replaces all current data and identity.'
            if self.cancel_event.is_set():
                self.cancel()
        accepted = self._submit('protecting', operation, prepared)
        if not accepted:
            password = None
        return accepted

    def apply(self, *, confirmed=False, acknowledged=False):
        if self.app.closing or self.phase != 'prepared' or not self._ticket or not confirmed or not acknowledged:
            return False
        ticket, self._ticket = self._ticket, None
        def completed(result):
            self.pending, self.phase = False, result.outcome.lower()
            self.message = result.message + (' ' + result.cleanup_warning if result.cleanup_warning else '')
            self.blocked = result.outcome == 'UNKNOWN'
            if result.outcome == 'RESTORED' and not self.app.closing:
                self.app.backup_restored()
            elif self.blocked and not self.app.closing:
                self.app.backup_unknown(self.message)
            if self.app.closing:
                self.app._shutdown_write_error = OfflineError('restore_outcome', self.message)
        accepted = self._submit('replacing', lambda owner, cancel, progress: owner.apply_restore(ticket, cancel=cancel), completed)
        if not accepted:
            self._ticket, self.phase, self.pending = ticket, 'prepared', True
            self.message = 'No replacement was queued. The prepared operation is still protected. Retry cancellation before leaving.'
        return accepted

    def cancel(self):
        self.cancel_event.set()
        if self.phase == 'prepared' and self._ticket:
            ticket, self._ticket = self._ticket, None
            def cancelled(result):
                self.pending, self.phase = False, 'cancelled'
                self.message = 'Replacement cancelled. Saved recovery backup remains available.'
            accepted = self._submit('cancelling', lambda owner, cancel, progress: owner.cancel_prepared(ticket), cancelled)
            if not accepted:
                # Owner maintenance is still active: do not advertise admission.
                self._ticket, self.phase, self.pending = ticket, 'prepared', True
                self.message = 'Prepared replacement could not be cancelled yet. Retry cancellation before closing.'
            return accepted
        if self.phase == 'preview':
            self.pending, self.phase = False, 'cancelled'
            self.preview = None
        elif self.pending:
            self.message = 'Cancellation requested. Waiting for verified outcome; completed saves remain saved.'

    shutdown = cancel

    def poll(self):
        value = self._progress.take()
        if value and self.pending and not self.cancel_event.is_set():
            self.message = str(value)
        render = getattr(getattr(self.app, 'screen', None), 'render_backup', None)
        if render and not self.app.closing:
            render()


def BackupView(parent, app):
    """Scrollable subordinate screen, usable before a local profile exists."""
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    from desktop.components.common import button, entry, label, checkbox
    from desktop.theme import color

    class View(ctk.CTkScrollableFrame):
        def __init__(self):
            super().__init__(parent, fg_color='transparent')
            self.app = app
            self.columnconfigure(0, weight=1)
            label(self, 'Backup & restore', 28).grid(row=0, column=0, sticky='w', pady=12)
            self.explanation = label(self, 'Complete Windows backups include all audits, archived records, history, receipts, '
                  'profile and installation identity. No list filters apply. Your locally declared name is not '
                  'verified authentication. Live data and reports remain unencrypted. Keep a long unique '
                  'passphrase separately: lost passwords cannot be reset.', wraplength=650,
                  justify='left', anchor='w')
            self.explanation.grid(row=1, column=0, sticky='ew', pady=12)
            label(self, 'Backup passphrase (15–128 characters)').grid(row=2, column=0, sticky='w')
            self.secret = entry(self, show='•')
            self.secret.grid(row=3, column=0, sticky='ew', pady=8)
            label(self, 'Confirm passphrase for creating a backup').grid(row=4, column=0, sticky='w')
            self.confirmation = entry(self, show='•')
            self.confirmation.grid(row=5, column=0, sticky='ew', pady=8)
            self.create_button = button(self, 'Save complete encrypted backup…', self.create)
            self.create_button.grid(row=6, column=0, sticky='w', pady=8)
            self.inspect_button = button(self, 'Open backup for authenticated preview…', self.inspect)
            self.inspect_button.grid(row=7, column=0, sticky='w', pady=8)
            self.status = label(self, '', wraplength=650, justify='left', anchor='w')
            self.status.grid(row=8, column=0, sticky='ew', pady=12)
            self.protect = button(self, 'Save and verify current recovery backup…', self.prepare)
            self.protect.grid(row=9, column=0, sticky='w', pady=8)
            self.acknowledgement = ctk.BooleanVar(value=False)
            self.ack = checkbox(self, text='I acknowledge complete replacement',
                                    variable=self.acknowledgement)
            self.ack.grid(row=10, column=0, sticky='w', pady=12)
            self.replace = button(self, 'Confirm complete replacement…', self.apply)
            self.replace.grid(row=11, column=0, sticky='w', pady=8)
            self.cancel_button = button(self, 'Cancel operation', app.backup_job.cancel)
            self.cancel_button.grid(row=12, column=0, sticky='w', pady=8)
            self.back_button = button(self, 'Back to welcome' if app.shell is None else 'Back to Settings & Tools', self.back)
            self.back_button.grid(row=13, column=0, sticky='w', pady=12)
            self.actions = (self.create_button, self.inspect_button, self.protect,
                            self.replace, self.cancel_button, self.back_button)
            self.bind('<Configure>', self.fit_content, add='+')
            self.render_backup()

        def fit_content(self, event):
            if event.widget is not self:
                return
            scale = self._get_widget_scaling()
            width = max(120, self.winfo_width() / scale - 24)
            self.explanation.configure(wraplength=min(650, width))
            self.status.configure(wraplength=min(650, width))
            action_width = min(360, width)
            for action in self.actions:
                # CTk buttons expose no public wrap option. Their native label uses
                # physical pixels; keep action height content-driven at every DPI.
                action.configure(width=action_width)
                action._text_label.configure(wraplength=round(max(80, action_width - 24) * scale))
                height = max(40, action._text_label.winfo_reqheight() / scale + 20)
                if action.cget('height') != height:
                    action.configure(height=height)

        def back(self):
            self.secrets()
            if app.backup_job.pending:
                app.backup_job.cancel()
                app._notice('Cancellation requested. Wait for the verified outcome before leaving.', False)
                return
            app.navigate('Local profile', force=True)

        def secrets(self):
            password, confirmation = self.secret.get(), self.confirmation.get()
            self.secret.delete(0, 'end')
            self.confirmation.delete(0, 'end')
            return password, confirmation

        def destination(self, title):
            return filedialog.asksaveasfilename(parent=app, title=title, defaultextension='.bhlibackup',
                filetypes=[('Encrypted Windows backup', '*.bhlibackup')], confirmoverwrite=False)

        def create(self):
            password, confirmation = self.secrets()
            try:
                app.backup_job.create(password, confirmation, self.destination('Save complete backup — choose a new filename'))
            finally:
                password = confirmation = None
            self.render_backup()

        def inspect(self):
            password, confirmation = self.secrets()
            self.acknowledgement.set(False)
            try:
                source = filedialog.askopenfilename(parent=app, title='Open Windows encrypted backup',
                    filetypes=[('Encrypted Windows backup', '*.bhlibackup')])
                app.backup_job.inspect(source, password)
            finally:
                password = confirmation = None
            self.render_backup()

        def prepare(self):
            password, confirmation = self.secrets()
            try:
                app.backup_job.prepare(password, self.destination('Protect current data — choose a new recovery filename'))
            finally:
                password = confirmation = None
            self.render_backup()

        def apply(self):
            if not self.acknowledgement.get():
                app._notice('Acknowledge the complete data and identity replacement first.')
                return
            accepted = messagebox.askokcancel('Replace all current offline data?',
                'The current recovery backup has been saved and verified. Replace all current data, profile '
                'and installation identity with this authenticated backup? Keep recovery files and retire duplicate identities.',
                parent=app, default=messagebox.CANCEL, icon=messagebox.WARNING)
            app.backup_job.apply(confirmed=accepted, acknowledged=self.acknowledgement.get())
            self.acknowledgement.set(False)
            self.render_backup()

        def render_backup(self):
            job = app.backup_job
            text = job.message
            if job.preview and job.phase in ('preview', 'protecting', 'prepared'):
                for title, state in (('Current', job.preview.current), ('Incoming', job.preview.candidate)):
                    profile = state['profile']
                    text += '\n\n' + title + ': ' + (profile['name'] + ' · ' + profile['id'] if profile else 'No profile')
                    text += '\nInstallation: ' + str(state['installation'])
                    text += '\n' + ', '.join(f'{key}: {value}' for key, value in state['counts'].items())
                    if state['metadata']:
                        text += '\nBackup metadata: ' + str(state['metadata'])
                text += '\n\nRe-enter this backup password to encrypt the mandatory current recovery backup.'
            self.status.configure(text=text)
            for control in (self.create_button, self.inspect_button):
                control.configure(state='normal' if not job.pending and not job.blocked else 'disabled')
            self.protect.configure(state='normal' if job.phase == 'preview' else 'disabled')
            self.replace.configure(state='normal' if job.phase == 'prepared' else 'disabled')
            self.ack.configure(state='normal' if job.phase == 'prepared' else 'disabled')

    return View()
