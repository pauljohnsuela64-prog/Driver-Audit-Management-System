"""Six-field create/edit presentation; operation state lives outside widgets."""
import tkinter as tk
import customtkinter as ctk

from desktop.api import ApiError
from desktop.audit_operations import (FIELDS,LABELS,LIMITS,ValidationError,normalize,
                                      changed_fields,CreationIntent,ambiguous,can_edit)
from desktop.components.common import button,entry,label,Notice,destroy_view
from desktop.theme import color,font


class AuditForm(ctk.CTkFrame):
    def __init__(self,parent,app,draft):
        super().__init__(parent,fg_color='transparent')
        self.app,self.draft=app,draft
        self.audit_id=draft.baseline.id if draft.baseline else None
        self.columnconfigure(0,weight=1)
        self.rowconfigure(2,weight=1)
        label(self,'Edit audit' if draft.baseline else 'Create audit',28).grid(row=0,column=0,sticky='w',pady=(0,8))
        self.notice=Notice(self)
        self.notice.configure(takefocus=1,wraplength=650)
        self.notice.grid(row=1,column=0,sticky='ew',pady=(0,8))
        self.body=ctk.CTkScrollableFrame(self,fg_color=color('surface'),corner_radius=12)
        self.body.grid(row=2,column=0,sticky='nsew')
        self.body.columnconfigure((0,1),weight=1,uniform='form')
        self.inputs,self.groups,self.errors={},{},{}
        for key in FIELDS:
            group=ctk.CTkFrame(self.body,fg_color='transparent')
            group.columnconfigure(0,weight=1)
            hint=' (optional)' if key in ('helper_name','remarks') else ' *'
            label(group,LABELS[key]+hint,14).grid(row=0,column=0,sticky='w',pady=(8,4))
            if key=='remarks':
                widget=ctk.CTkTextbox(group,height=150,wrap='word',font=font(),fg_color=color('raised'),
                    text_color=color('text'),border_width=1,border_color=color('border'))
                widget.insert('1.0',draft.values.get(key) or '')
            else:
                widget=entry(group,'YYYY-MM-DD' if key=='audit_date' else '')
                widget.insert(0,draft.values.get(key) or '')
            widget.grid(row=1,column=0,sticky='ew')
            hint_text='YYYY-MM-DD · years 1000–9999' if key=='audit_date' else f'Maximum {LIMITS[key]:,} characters'
            label(group,hint_text,12,True).grid(row=2,column=0,sticky='w',pady=(4,0))
            error=label(group,'',12,justify='left',wraplength=300)
            error.configure(text_color=color('error'))
            error.grid(row=3,column=0,sticky='ew')
            self.inputs[key],self.groups[key],self.errors[key]=widget,group,error
        self.attribution=label(self.body,'',14,justify='left',wraplength=650)
        self.comparison=ctk.CTkFrame(self.body,fg_color=color('raised'))
        footer=ctk.CTkFrame(self,fg_color='transparent')
        footer.grid(row=3,column=0,sticky='ew',pady=(12,0))
        button(footer,'Cancel',lambda:app.navigate('Driver Audits'),width=110).pack(side='left')
        self.save_button=button(footer,'Save audit',self.save,True,width=180)
        self.save_button.pack(side='right')
        self.reload_button=button(footer,'Compare latest',self.fetch_latest,width=160)
        self.reload_button.pack(side='right',padx=8)
        self._columns=None
        tk.Misc.bind(self,'<Configure>',self.resize,add='+')
        self.layout(1)
        self.render_state()

    def resize(self,event):
        if event.widget is self:
            width=event.width/self._get_widget_scaling()
            self.layout(2 if width>=850 else 1)
            self.notice.configure(wraplength=max(250,int(width)-24))

    def layout(self,columns):
        if columns==self._columns:
            return
        self._columns=columns
        for i,key in enumerate(FIELDS):
            self.groups[key].grid(row=i//columns,column=i%columns,sticky='nsew',padx=16,pady=(4,0))
        row=(len(FIELDS)+columns-1)//columns
        self.attribution.grid(row=row,column=0,columnspan=columns,sticky='ew',padx=16,pady=16)
        self.comparison.grid(row=row+1,column=0,columnspan=columns,sticky='ew',padx=16,pady=(0,16))

    def capture(self):
        if not self.draft.pending and not (self.draft.intent and self.draft.uncertain):
            self.draft.values={key:(widget.get('1.0','end-1c') if key=='remarks' else widget.get())
                               for key,widget in self.inputs.items()}

    def render_state(self):
        draft=self.draft
        frozen=draft.pending or bool(draft.intent and draft.uncertain)
        for key,widget in self.inputs.items():
            widget.configure(state='disabled' if frozen else 'normal')
            self.errors[key].configure(text=draft.errors.get(key,''))
        self.notice.show(draft.message or ('Saving… Do not close this window until the result is known.' if draft.pending else
            'Fields marked * are required. Audited By is supplied by the server.'),bool(draft.message))
        self.save_button.configure(text='Saving…' if draft.pending else 'Retry same creation' if draft.intent and draft.uncertain else 'Save audit',
            state='disabled' if draft.pending or draft.baseline and (draft.uncertain or draft.latest is not None) else 'normal')
        self.reload_button.configure(state='normal' if draft.baseline and not draft.pending else 'disabled')
        snapshot=draft.baseline.audited_by_name if draft.baseline else self.app.session.login.user.full_name
        self.attribution.configure(text=f'Audited By (read-only): {snapshot}'+(' · server confirms on save' if not draft.baseline else '\nOriginal historical attribution is preserved.'))
        for child in self.comparison.winfo_children():
            destroy_view(child)
        if draft.latest:
            label(self.comparison,'This audit changed — review before saving again',18,wraplength=500,justify='left').pack(anchor='w',padx=12,pady=12)
            for key in FIELDS:
                baseline=getattr(draft.baseline,key)
                latest=getattr(draft.latest,key)
                local=draft.values.get(key)
                if local!=baseline or latest!=baseline:
                    text=f'{LABELS[key]}\nOriginal: {baseline or "Not provided"}\nYour draft: {local or "Not provided"}\nLatest: {latest or "Not provided"}'
                    box=ctk.CTkTextbox(self.comparison,height=140,wrap='word',font=font(),fg_color=color('surface'),text_color=color('text'))
                    box.insert('1.0',text);box.configure(state='disabled')
                    box.pack(fill='x',padx=12,pady=6)
            button(self.comparison,'Keep my changed fields; review form',self.reapply,True).pack(fill='x',padx=12,pady=8)
            button(self.comparison,'Discard my draft and load latest',self.reload_latest).pack(fill='x',padx=12,pady=(0,12))

    def save(self):
        draft=self.draft
        if draft.pending or draft.latest is not None or draft.baseline and draft.uncertain:
            return
        self.capture()
        draft.errors={}
        try:
            data=normalize(draft.values)
        except ValidationError as error:
            draft.errors=error.errors
            draft.message='Please correct: '+', '.join(LABELS.get(key,'Form') for key in error.errors)+'.'
            self.render_state();self.notice.focus_set()
            return
        client,login=self.app.client,self.app.session.login
        if draft.baseline:
            if not can_edit(draft.baseline,login.user.id,login.user.role):
                draft.message='You no longer have permission to edit this record.';self.render_state();return
            payload=changed_fields(draft.baseline,data)
            if not payload:
                draft.message='No changes to save.';self.render_state();return
            record_id,etag=draft.baseline.id,draft.baseline.etag
            work=lambda:client.update_audit(login.token,record_id,payload,etag)
        else:
            if draft.intent is None:
                draft.intent=CreationIntent(login.user.id,data)
            payload,key=draft.intent.payload,draft.intent.key
            work=lambda:client.create_audit(login.token,payload,key)
        draft.pending=True;draft.message=''
        app=self.app
        def completed(record,error):
            draft.pending=False
            if error:
                draft.message=str(error)
                if draft.baseline:
                    draft.uncertain=ambiguous(error) or error.status in (409,412)
                else:
                    # Preserve an already-ambiguous intent even when a later retry is rate limited.
                    draft.uncertain=draft.uncertain or ambiguous(error) or error.status==409
                    if not draft.uncertain:
                        draft.intent=None
                if draft.uncertain:
                    draft.message+=(' Outcome not confirmed. Retry only this same creation.' if not draft.baseline else
                                    ' Compare the latest record before saving again.')
                app.render_draft()
                if draft.baseline and draft.uncertain:
                    app.screen.fetch_latest()
                return
            app.draft=None
            app.selected_id=record.id
            app.navigate('Audit Details',record.id,force=True)
            app.shell.notice.show('Audit saved. Current server state is shown; list filters are preserved.',False)
        app.mutate(work,completed)
        if app.draft is draft:
            app.render_draft()

    def fetch_latest(self):
        draft=self.draft
        if draft.pending or not draft.baseline:
            return
        self.capture()
        app,client,token,audit_id=self.app,self.app.client,self.app.session.login.token,draft.baseline.id
        draft.uncertain=True
        def loaded(record,error):
            if error:
                draft.message=str(error)+' Your draft is retained; saving is blocked until the record can be reviewed.'
            else:
                draft.latest=record
                draft.message='Compare original, your draft, and latest server values below.'
            app.render_draft()
        app.request(lambda:client.get_audit(token,audit_id),loaded)
        self.render_state()

    def reapply(self):
        draft=self.draft
        if not draft.latest:
            return
        # Preserve only the user's changes, retaining unrelated new server values.
        changes=changed_fields(draft.baseline,draft.values)
        from desktop.audit_operations import record_values
        draft.values=record_values(draft.latest)|changes
        draft.baseline=draft.latest
        draft.latest=None;draft.uncertain=False
        draft.message='Latest version loaded with your changed fields. Review all values, then Save.'
        self.app.rebuild_form()

    def reload_latest(self):
        if self.draft.latest:
            from desktop.audit_operations import record_values
            self.draft.baseline=self.draft.latest
            self.draft.values=record_values(self.draft.latest)
            self.draft.latest=None;self.draft.uncertain=False;self.draft.message='Latest values loaded.'
            self.app.rebuild_form()
