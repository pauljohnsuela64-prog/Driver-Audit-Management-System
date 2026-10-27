"""Application-owned export job; workers receive data, never Tk widgets."""
from datetime import datetime, timezone
from queue import Queue, Empty
from tkinter import filedialog
import os
import time

from desktop.api import ApiError
from desktop.components.audit_dialogs import confirm
from desktop.reports import Destination, ExportControl, export_audits, query_summary, CAVEAT
from desktop.tasks import Tasks


class ExportJob:
    def __init__(self,app):
        self.app=app;self.tasks=Tasks(workers=1,capacity=1)
        self.pending=False;self.message='';self.result=None;self.control=None
        self.progress=Queue(maxsize=1)
        self._last_render=None

    def start(self,query,destination):
        if self.pending or not self.app.session.login:return
        self.pending=True;self.result=None;self.message='Preparing export…'
        control=self.control=ExportControl()
        login=self.app.session.login
        control.deadline=time.monotonic()+max(0,(login.expires_at-datetime.now(timezone.utc)).total_seconds())
        generation=self.app.session.generation
        client,token=self.app.client,login.token
        updates=self.progress
        def progress(value):
            try:updates.get_nowait()
            except Empty:pass
            updates.put_nowait(value)
        def finished(result,error):
            self.pending=False
            if generation!=self.app.session.generation:
                self.message='';self.result=None;return
            if error and error.status==401:
                self.app.logout('Your session expired during export. Please sign in again.'+
                    (' '+str(error) if 'temporary files' in str(error) else ''),force=True);return
            self.result=result
            self.message=(str(error) if error else 'No matching audits. No report saved.' if not result.count else
                          f'Excel report saved · {result.count:,} records · {result.path}')
            self.render()
        if not self.tasks.submit('export',lambda:export_audits(client,token,query,destination,control,progress),finished):
            self.pending=False;self.message='Export is busy. Wait for cancellation to finish and retry.'
        self.render()

    def poll(self):
        try:
            count,stage=self.progress.get_nowait()
            if self.pending:self.message=f'{stage} · {count:,} records processed'
        except Empty:pass
        self.tasks.drain();self.render()

    def render(self):
        screen=self.app.screen
        state=(id(screen),self.pending,self.message,self.result)
        if state!=self._last_render and screen and hasattr(screen,'render_export'):
            self._last_render=state;screen.render_export()

    def cancel(self):
        if self.control:self.control.cancel()
        if self.pending:self.message='Cancelling export… waiting for the current operation to finish.'
        self.render()

    def clear_session(self):
        self.cancel();self.result=None;self.message=''

    def close(self):
        self.clear_session();self.tasks.close()


def choose_export(screen):
    app=screen.app
    if app.export_job.pending:return
    if not screen.loaded or screen.filter_state()!=screen.applied_filters:
        screen.notice.show('Apply search and filters and wait for results before exporting.');return
    query=app.query
    def choose():
        if not app.session.login:return
        selected=filedialog.asksaveasfilename(parent=app,title='Export audits to Excel',
            defaultextension='.xlsx',filetypes=[('Excel workbook','*.xlsx')],
            initialfile=f'DAMS-audits-{datetime.now().strftime("%Y-%m-%d")}.xlsx',confirmoverwrite=True)
        if not selected:return
        try:destination=Destination.capture(selected)
        except ApiError as error:
            app.export_job.message=str(error);app.export_job.render();return
        if destination.stamp is not None:
            app.export_job.message='Choose a new filename. Existing workbooks are never replaced.'
            app.export_job.render()
        else:app.export_job.start(query,destination)
    confirm(app,'Export all matching audits',
        'Export all pages using these applied filters:\n\n'+query_summary(query,app.session.login.user.id)+'\n\n'+CAVEAT+
        '\n\nReports are unencrypted local files. Choose a protected folder. Limits: 20,000 records and 10 minutes.',
        choose,'Choose save location')


def open_folder(app):
    result=app.export_job.result
    if result and result.count:
        try:os.startfile(str(result.path.parent))
        except OSError:
            app.export_job.message='The report is saved, but its folder could not be opened.'
            app.export_job.render()
