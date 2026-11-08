"""Tk transfer controls; repository and file work stay on the owning worker."""
from dataclasses import replace
from tkinter import filedialog
import customtkinter as ctk
from desktop.components.common import button, entry, label, Notice
from desktop.offline.models import valid_date
from desktop.offline.transfer_controller import TransferController, confirm_import
from desktop.theme import color

WARNING = ('Transfer files are plaintext and names are locally declared. '
           'Transfer copies selected audits and history; it is not backup/restore or synchronization. '
           'Existing identities are never merged. Archived audits are included.')

class TransferView(ctk.CTkScrollableFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color='transparent')
        self.app = app
        self.controller = TransferController(app, self)
        self.raw = self.preview_result = None
        self.columnconfigure(0, weight=1)
        label(self, 'Transfer audits', 28).grid(row=0, column=0, sticky='w', pady=(0,12))
        self.warning=label(self, WARNING, wraplength=440, justify='left')
        self.warning.grid(row=1,column=0,sticky='ew',pady=(0,20))
        self.selection_note=label(self, 'Export all audits, or enter an inclusive audit-date range. Blank dates include all dates.', wraplength=440, justify='left')
        self.selection_note.grid(row=2,column=0,sticky='ew')
        fields = ctk.CTkFrame(self, fg_color=color('surface'))
        fields.grid(row=3,column=0,sticky='ew',pady=12)
        fields.columnconfigure((0,1),weight=1)
        label(fields,'From (YYYY-MM-DD)').grid(row=0,column=0,sticky='w',padx=12,pady=(12,4))
        label(fields,'Through (YYYY-MM-DD)').grid(row=0,column=1,sticky='w',padx=12,pady=(12,4))
        self.date_from = entry(fields); self.date_to = entry(fields)
        self.date_from.grid(row=1,column=0,sticky='ew',padx=12,pady=(0,12))
        self.date_to.grid(row=1,column=1,sticky='ew',padx=12,pady=(0,12))
        self.export_button=button(self,'Prepare export',self.export,True)
        self.export_button.grid(row=4,column=0,sticky='w',pady=8)
        self.import_button=button(self,'Open transfer file',self.open_import)
        self.import_button.grid(row=5,column=0,sticky='w',pady=8)
        self.progress=ctk.CTkProgressBar(self,mode='indeterminate')
        self.progress.grid(row=6,column=0,sticky='ew',pady=12); self.progress.grid_remove()
        self.notice=Notice(self); self.notice.grid(row=7,column=0,sticky='ew')
        self.counts=label(self,'No file selected.',wraplength=440,justify='left')
        self.counts.grid(row=8,column=0,sticky='ew',pady=12)
        self.apply_button=button(self,'Import new records only',self.confirm_import,True)
        self.apply_button.grid(row=9,column=0,sticky='w',pady=8); self.apply_button.configure(state='disabled')
        self.cancel_button=button(self,'Cancel',self.cancel)
        self.cancel_button.grid(row=10,column=0,sticky='w',pady=8); self.cancel_button.configure(state='disabled')
        button(self,'View refreshed audits',lambda: app.navigate('Driver Audits')).grid(row=11,column=0,sticky='w',pady=12)
        self._parent_canvas.bind('<Configure>',self.resize,add='+')

    def resize(self,event):
        width=max(240,int(event.width/self._get_widget_scaling())-32)
        for widget in (self.warning,self.selection_note,self.counts,self.notice):
            widget.configure(wraplength=width)

    def status(self,message,busy=False,error=False):
        self.notice.show(message,error)
        for widget in (self.export_button,self.import_button,self.date_from,self.date_to):
            widget.configure(state='disabled' if busy else 'normal')
        self.apply_button.configure(state='normal' if not busy and self.preview_result is not None else 'disabled')
        self.cancel_button.configure(state='normal' if busy or self.preview_result is not None else 'disabled')
        if busy: self.progress.grid(); self.progress.start()
        else: self.progress.stop(); self.progress.grid_remove()

    def export(self):
        start=self.date_from.get().strip() or None; end=self.date_to.get().strip() or None
        if any(value is not None and not valid_date(value) for value in (start,end)) or (start and end and start>end):
            self.status('Enter valid dates in YYYY-MM-DD order, or leave both blank for all audits.',error=True)
            return
        self.clear_preview()
        self.controller.export(start,end)

    def clear_preview(self):
        self.raw=self.preview_result=None
        self.apply_button.configure(state='disabled')

    def export_ready(self,raw,records,events):
        self.status(f'Export ready: {records} audits and {events} history events. Choose a new filename.')
        self.counts.configure(text=f'Export selection: {records} audits | {events} history events | archived audits included')
        path=filedialog.asksaveasfilename(parent=self.app,title='Save audit transfer using a new filename',defaultextension='.bhlitransfer',filetypes=[('BHLI audit transfer','*.bhlitransfer')],confirmoverwrite=False)
        if path: self.controller.publish(raw,path)
        else: self.status('Export file selection cancelled. No file was saved.')

    def export_finished(self,cleanup):
        self.status('Transfer file saved and flushed.' + ('' if cleanup else ' The completed file is available, but a temporary sibling could not be removed.'))

    def open_import(self):
        self.clear_preview()
        path=filedialog.askopenfilename(parent=self.app,title='Open audit transfer',filetypes=[('BHLI audit transfer','*.bhlitransfer')])
        if path: self.controller.preview(path)

    def preview_ready(self,raw,preview):
        self.raw,self.preview_result=raw,preview
        self.counts.configure(text=f'New: {len(preview.new_ids)} | Already here: {len(preview.duplicate_ids)} | Different version: {len(preview.conflict_ids)}. Duplicates and conflicts are skipped. Only new audits will be added. Existing audits and their history stay unchanged. Later edits to audits already imported are not synchronized. Your local profile remains unchanged.')
        self.status('Validation complete. Review the counts before confirming import.')

    def cancel(self):
        if self.controller.pending:
            self.controller.cancel()
        else:
            self.clear_preview()
            self.counts.configure(text='Import preview cancelled. No import was submitted.')
            self.status('Choose another transfer file when ready.')

    def confirm_import(self):
        from desktop.components.audit_dialogs import confirm
        confirm_import(self, confirm)

    def import_finished(self,result):
        self.clear_preview()
        self.app.query = replace(self.app.query,page=1)
        self.app.selected_id=None
        # Navigating creates the ordinary audit list and requests fresh rows.
        self.app.navigate('Driver Audits',force=True)
        self.app._notice(f'Import confirmed: {result.imported} new, {result.duplicates} duplicates skipped, {result.conflicts} conflicts skipped. Original attribution and history are preserved.',False)
