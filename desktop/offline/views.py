"""Small local-only views alongside the shared audit screens."""
import customtkinter as ctk

from desktop.components.common import button, entry, label, Notice, option_menu
from desktop.offline.models import OfflineError, normalize_name
from desktop.theme import color, font


class ProfileView(ctk.CTkScrollableFrame):
    def __init__(self, parent, app, welcome=False):
        super().__init__(parent, fg_color='transparent')
        self.app = app
        self.welcome = welcome
        self.pending = False
        self.columnconfigure(0, weight=1)
        if welcome:
            from desktop.resources import company_logo
            self.logo = company_logo(320)
            ctk.CTkLabel(self, text='', image=self.logo).grid(row=0, column=0, pady=(24, 12))
        label(self, 'Welcome to BHLI Audit' if welcome else 'Settings & Tools', 28).grid(
            row=1, column=0, pady=(0, 12))
        label(self, 'Enter your auditor name to continue. No password required.' if welcome else
              'This name is recorded with new audits. Original auditor names stay unchanged.',
              muted=True, wraplength=580, justify='left').grid(row=2, column=0, pady=(0, 12))
        # Keep a visible label and keyboard submission; this is not account authentication.
        panel = ctk.CTkFrame(self, fg_color=color('surface'), corner_radius=12, width=520)
        if not welcome:
            label(self, 'Local Auditor Profile', 20).grid(row=3, column=0, sticky='w', pady=(12, 8))
        panel.grid(row=4, column=0, sticky='' if welcome else 'ew')
        panel.columnconfigure(0, weight=1)
        label(panel, 'Auditor name *').grid(row=0, column=0, sticky='w', padx=24, pady=(24, 4))
        self.name = entry(panel)
        if welcome:
            self.name.configure(width=440)
        self.name.grid(row=1, column=0, sticky='ew', padx=24)
        self.name.insert(0, app.profile.name if app.profile else '')
        self.name.bind('<Return>', lambda event: self.save())
        self.name.focus_set()
        label(panel, 'Maximum 200 characters. Existing auditor names are preserved.',
              12, True, wraplength=500).grid(row=2, column=0, sticky='w', padx=24, pady=(4, 12))
        self.notice = Notice(panel)
        self.notice.grid(row=3, column=0, sticky='ew', padx=24)
        self.save_button = button(panel, 'Continue' if welcome else 'Save local profile', self.save, True, width=180)
        self.save_button.grid(row=4, column=0, sticky='w', padx=24, pady=24)
        if not welcome:
            label(self, 'Backups replace the complete Windows installation state. Transfer audits copies selected '
              'audits between platforms. Save any edited profile name before leaving this screen.',
              muted=True, wraplength=580, justify='left').grid(row=5, column=0, sticky='ew', pady=(20, 8))
        if not welcome:
            label(self, 'Backup & Restore', 20).grid(row=6, column=0, sticky='w', pady=(12, 8))
        self.backup_button = button(self, 'Backup & restore…', app.open_backup, width=360)
        self.backup_button.grid(row=7, column=0, sticky='w', pady=(0, 20))
        if not welcome:
            label(self, 'Manual Data Transfer', 20).grid(row=8, column=0, sticky='w', pady=(12, 8))
            self.transfer_button = button(self, 'Transfer audits…', app.open_transfer, width=360)
            self.transfer_button.grid(row=9, column=0, sticky='w', pady=(0, 20))
            label(self, 'Appearance', 20).grid(row=10, column=0, sticky='w', pady=(12, 8))
            self.appearance = option_menu(self, values=['Light', 'Dark'], command=app.set_theme,
                                          width=160, font=font(), fg_color=color('primary'),
                                          text_color=color('on_primary'))
            self.appearance.set(ctk.get_appearance_mode())
            self.appearance.grid(row=11, column=0, sticky='w', pady=(0, 20))
        controls = [self.name, self.save_button, self.backup_button]
        if not welcome:
            controls.extend((self.transfer_button, self.appearance))
        for control in controls:
            control.bind('<FocusIn>', lambda event, target=control: self.reveal(target), add='+')

    def reveal(self, control):
        canvas = self._parent_canvas
        top = control.winfo_rooty() - self.winfo_rooty()
        bottom = top + control.winfo_height()
        visible_top, height = canvas.canvasy(0), canvas.winfo_height()
        region = canvas.bbox('all')
        if region and region[3] > height and (top < visible_top or bottom > visible_top + height):
            target = max(0, top - 12) if top < visible_top else bottom - height + 12
            canvas.yview_moveto(target / max(1, region[3]))

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
                self.save_button.configure(state='normal', text='Continue' if self.welcome else 'Save local profile')
                self.name.configure(state='normal')
                return
            first = app.profile is None
            app.profile = profile
            if self.welcome:
                app._entered = True
            app.rebuild_shell('Driver Audits' if first or self.welcome else 'Settings & Tools')
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
