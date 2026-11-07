"""Small local-only views alongside the shared audit screens."""
import customtkinter as ctk

from desktop.components.common import button, entry, label, Notice
from desktop.offline.models import OfflineError, normalize_name
from desktop.theme import color, font


WARNING = ('Development edition · Use fictional data only. This device holds the only copy. '
           'Losing this Windows profile or its database permanently loses the records. '
           'Use complete encrypted backups and keep their passphrase separately. Reports are unencrypted.')


class ProfileView(ctk.CTkScrollableFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color='transparent')
        self.app = app
        self.pending = False
        self.columnconfigure(0, weight=1)
        label(self, 'Local auditor profile', 28).grid(row=0, column=0, sticky='w', pady=(0, 12))
        label(self, 'Your name is locally declared. It is not verified authentication.',
              muted=True, wraplength=580, justify='left').grid(row=1, column=0, sticky='w', pady=(0, 12))
        label(self, WARNING, wraplength=580, justify='left').grid(row=2, column=0, sticky='ew', pady=(0, 24))
        panel = ctk.CTkFrame(self, fg_color=color('surface'), corner_radius=12)
        panel.grid(row=3, column=0, sticky='ew')
        panel.columnconfigure(0, weight=1)
        label(panel, 'Auditor name *').grid(row=0, column=0, sticky='w', padx=24, pady=(24, 4))
        self.name = entry(panel)
        self.name.grid(row=1, column=0, sticky='ew', padx=24)
        self.name.insert(0, app.profile.name if app.profile else '')
        self.name.bind('<Return>', lambda event: self.save())
        label(panel, 'Maximum 200 characters. Existing auditor names are preserved.',
              12, True, wraplength=500).grid(row=2, column=0, sticky='w', padx=24, pady=(4, 12))
        self.notice = Notice(panel)
        self.notice.grid(row=3, column=0, sticky='ew', padx=24)
        self.save_button = button(panel, 'Save local profile', self.save, True, width=180)
        self.save_button.grid(row=4, column=0, sticky='w', padx=24, pady=24)
        label(self, 'Backups replace the complete Windows installation state. Transfer audits copies selected '
              'audits between platforms. Save any edited profile name before leaving this screen.',
              muted=True, wraplength=580, justify='left').grid(row=4, column=0, sticky='ew', pady=(20, 8))
        button(self, 'Backup & restore…', app.open_backup).grid(
            row=5, column=0, sticky='w', pady=(0, 20))

    def save(self):
        if self.pending or self.app.closing:
            return
        try:
            name = normalize_name(self.name.get())
        except OfflineError:
            self.notice.show('Enter your name using 1–200 characters.')
            self.name.focus_set()
            return
        self.pending = True
        self.save_button.configure(state='disabled', text='Saving…')
        self.name.configure(state='disabled')
        app = self.app
        def completed(profile, error):
            self.pending = False
            if app.closing:
                return
            if error:
                self.notice.show(str(error) + ' Retry saving the profile.')
                self.save_button.configure(state='normal', text='Save local profile')
                self.name.configure(state='normal')
                return
            first = app.profile is None
            app.profile = profile
            app.rebuild_shell('Dashboard' if first else 'Local profile')
            app.shell.notice.show('Local profile saved. Historical auditor names are unchanged.', False)
        app.mutate(lambda repo: repo.save_profile(name), completed)


def render_history_event(parent, event):
    before, after = event.before, event.after
    from desktop.offline.presentation import FIELDS
    from desktop.audit_operations import LABELS
    lines = [f'Original auditor: {after.audited_by_name}',
             f'Action by: {event.actor_name} · locally declared name']
    for key in (*FIELDS, 'audited_by_name'):
        old = getattr(before, key) if before else None
        new = getattr(after, key)
        if before is None or event.action == 'ARCHIVE' or old != new:
            lines.extend(['', LABELS.get(key, 'Audited By'),
                          'Before: ' + (old or 'Not provided') if before else 'Before: No record',
                          'After: ' + (new or 'Not provided')])
    lines.extend(['', f'Event {event.id}', f'Record {after.id} · Revision {after.revision}',
                  f'Actor profile {event.actor_profile_id}',
                  f'Archived at: {after.archived_at:%Y-%m-%d %H:%M:%S UTC}'
                  if after.archived_at else 'Archive state: Active'])
    box = ctk.CTkTextbox(parent, height=300, wrap='word', font=font(),
                        fg_color=color('surface'), text_color=color('text'),
                        border_width=1, border_color=color('border'))
    box.insert('1.0', '\n'.join(lines))
    box.configure(state='disabled')
    box.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 12))
