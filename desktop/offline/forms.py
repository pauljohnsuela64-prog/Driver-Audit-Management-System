"""Use the existing six-field layout with local-only save/conflict semantics."""
import customtkinter as ctk

from desktop.audit_operations import LABELS, LIMITS
from desktop.components.common import button, label, destroy_view
from desktop.offline.models import OfflineError, normalize_values, normalize_text, valid_date
from desktop.offline.presentation import FIELDS, record_values
from desktop.screens.audit_form import AuditForm
from desktop.theme import color, font


def field_errors(values):
    errors = {}
    for key in FIELDS:
        try:
            value = values.get(key)
            if key == 'audit_date':
                if not valid_date(value):
                    errors[key] = 'Use a real YYYY-MM-DD date (years 1000–9999).'
            elif value is None and key in ('helper_name', 'remarks'):
                continue
            else:
                normalize_text(value, LIMITS[key], optional=key in ('helper_name', 'remarks'))
        except OfflineError:
            errors[key] = f'Enter text, maximum {LIMITS[key]:,} characters.'
    return errors


class OfflineAuditForm(AuditForm):
    def capture(self):
        if not self.draft.pending and not self.draft.uncertain and self.draft.latest is None:
            self.draft.values = {key: (widget.get('1.0', 'end-1c') if key == 'remarks' else widget.get())
                                 for key, widget in self.inputs.items()}

    def render_state(self):
        draft = self.draft
        frozen = draft.pending or draft.uncertain or draft.latest is not None or draft.unavailable
        for key, widget in self.inputs.items():
            widget.configure(state='disabled' if frozen else 'normal')
            self.errors[key].configure(text=draft.errors.get(key, ''))
        self.notice.show(draft.message or (
            'Saving locally… Please wait for the result.' if draft.pending else
            'Fields marked * are required. Your local profile supplies Audited By.'), bool(draft.message))
        self.save_button.configure(
            text='Saving…' if draft.pending else 'Retry same creation' if draft.intent and draft.uncertain else 'Save audit',
            state='disabled' if draft.pending or draft.unavailable or draft.latest is not None or
                  draft.baseline and draft.uncertain else 'normal')
        self.reload_button.configure(state='normal' if draft.baseline and not draft.pending else 'disabled')
        name = draft.baseline.audited_by_name if draft.baseline else self.app.profile.name
        self.attribution.configure(text=f'Audited By (read-only): {name}\n' + (
            'Original historical attribution is preserved.' if draft.baseline else
            'Locally declared name; not verified authentication.'))
        for child in self.comparison.winfo_children():
            destroy_view(child)
        if draft.latest is not None:
            label(self.comparison, 'Compare your draft with the latest local revision', 18,
                  wraplength=500, justify='left').pack(anchor='w', padx=12, pady=12)
            for key in FIELDS:
                baseline, latest, local = getattr(draft.baseline, key), getattr(draft.latest, key), draft.values.get(key)
                if local != baseline or latest != baseline:
                    text = (f'{LABELS[key]}\nOriginal: {baseline or "Not provided"}\n'
                            f'Your draft: {local or "Not provided"}\nLatest: {latest or "Not provided"}')
                    box = ctk.CTkTextbox(self.comparison, height=140, wrap='word', font=font(),
                                        fg_color=color('surface'), text_color=color('text'))
                    box.insert('1.0', text)
                    box.configure(state='disabled')
                    box.pack(fill='x', padx=12, pady=6)
            button(self.comparison, 'Discard my draft and load latest', self.reload_latest).pack(
                fill='x', padx=12, pady=(8, 12))

    def save(self):
        draft, app = self.draft, self.app
        if app.closing or app.mutation_pending or draft.pending or draft.unavailable or draft.latest is not None or draft.baseline and draft.uncertain:
            return
        self.capture()
        try:
            data = normalize_values(draft.values)
        except OfflineError:
            draft.errors = field_errors(draft.values)
            draft.message = 'Correct the indicated fields before saving.'
            self.render_state()
            self.notice.focus_set()
            return
        draft.errors = {}
        if draft.baseline:
            if data == record_values(draft.baseline):
                draft.message = 'No changes to save.'
                self.render_state()
                return
            identity, revision = draft.baseline.id, draft.baseline.revision
            work = lambda repo: repo.update(identity, revision, data)
        else:
            identity, payload = draft.creation()
            work = lambda repo: repo.create(identity, payload)
        draft.pending, draft.message = True, ''
        def completed(record, error):
            draft.pending = False
            if app.closing:
                return
            if error:
                definitive = error.code in ('validation', 'profile_required', 'not_found', 'queue')
                if draft.baseline:
                    draft.unavailable = error.code == 'not_found'
                    draft.uncertain = not definitive
                    draft.message = str(error) + (' Compare the latest revision before saving again.' if draft.uncertain else '')
                else:
                    draft.uncertain = draft.uncertain or not definitive
                    if not draft.uncertain:
                        draft.intent = None
                    draft.message = str(error) + (
                        ' Outcome not confirmed. Retry only this same creation, or discard and inspect local records.'
                        if draft.uncertain else ' Correct the form and retry.')
                app.render_draft()
                return
            app.draft = None
            app.saved(record.id)
        app.mutate(work, completed)
        app.render_draft()

    def fetch_latest(self):
        draft, app = self.draft, self.app
        if draft.pending or not draft.baseline or app.closing:
            return
        self.capture()
        draft.uncertain = True
        draft.message = 'Loading latest local revision for comparison…'
        def loaded(record, error):
            if error:
                draft.unavailable = error.code == 'not_found'
                draft.message = str(error) + ' Draft retained. Compare latest again before saving.'
            else:
                draft.latest = record
                draft.unavailable = bool(record.deleted_at)
                draft.message = ('This record is archived and read-only. Discard the draft to load it.'
                                 if draft.unavailable else 'Review the comparison below. Loading latest discards your draft; saving is a separate action.')
            app.render_draft()
        app.read_audit(draft.baseline.id, loaded)
        self.render_state()

    def reload_latest(self):
        draft = self.draft
        if draft.latest is None:
            return
        if draft.latest.deleted_at:
            identity = draft.latest.id
            self.app.draft = None
            self.app.navigate('Audit Details', identity, force=True)
            return
        draft.baseline = draft.latest
        draft.values = record_values(draft.latest)
        draft.latest, draft.uncertain, draft.unavailable = None, False, False
        draft.message = 'Latest local revision loaded. Review the form before saving.'
        draft.errors = {}
        self.app.rebuild_form()
