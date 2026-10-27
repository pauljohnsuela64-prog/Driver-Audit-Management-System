"""Bounded, Tk-independent REST-to-XLSX export. No credentials are persisted."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Event
import os
import re
import shutil
import tempfile
import time
import sys

import xlsxwriter

from desktop.api import ApiError

HEADERS=('Driver Name','Helper Name','Audit Date','Station','Plate Number','Remarks','Audited By','Record ID','Status')
CAVEAT=('This export uses offset pagination, not a point-in-time snapshot. Concurrent changes can cause omissions '
        'or mixed versions even when counts match. Export while other administrators are not editing.')


class ExportError(ApiError):
    def __init__(self,message):super().__init__(message=message)


@dataclass(frozen=True)
class Limits:
    rows: int=20_000
    pages: int=200
    payload: int=100*1024*1024
    workspace: int=256*1024*1024
    seconds: float=600


def fingerprint(path):
    try:
        stat=path.lstat()
    except FileNotFoundError:return None
    if path.is_symlink() or not path.is_file():raise ExportError('Choose a regular .xlsx destination file.')
    return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


@dataclass(frozen=True)
class Destination:
    path: Path
    stamp: tuple | None

    @classmethod
    def capture(cls,path):
        path=Path(path).absolute()
        name=path.name
        if (path.suffix.lower()!='.xlsx' or name.endswith((' ','.')) or
            re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or
            re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',name,re.I) or
            not path.parent.is_dir()):
            raise ExportError('Choose a valid .xlsx file in an existing folder.')
        try:return cls(path,fingerprint(path))
        except OSError:raise ExportError('The destination could not be inspected. Choose another file.') from None


class ExportControl:
    """The final cancellation check is the commit decision; UI never waits on IO."""
    def __init__(self):self._lock=Lock();self._cancelled=Event();self.published=False;self.deadline=None
    def cancel(self):
        self._cancelled.set()
    def check(self):
        with self._lock:
            if self.deadline is not None and time.monotonic()>=self.deadline:raise ApiError(401)
            if self._cancelled.is_set() and not self.published:raise ExportError('Export cancelled. No report was saved.')
    def commit(self,source,destination,deadline=None):
        with self._lock:
            if self.deadline is not None and time.monotonic()>=self.deadline:raise ApiError(401)
            if deadline is not None and time.monotonic()>=deadline:
                raise ExportError('Export time limit reached. Narrow the filters and retry.')
            if self._cancelled.is_set():raise ExportError('Export cancelled. No report was saved.')
            publish(source,destination)
            self.published=True


def publish(source,destination):
    if fingerprint(destination.path)!=destination.stamp:
        raise ExportError('The destination changed during export. Choose the file again before retrying.')
    if destination.stamp is not None:
        raise ExportError('Choose a new filename. Existing workbooks are never replaced.')
    # Atomic no-clobber publication, including a file created after fingerprint().
    os.link(source,destination.path)


@dataclass(frozen=True)
class ExportResult:
    path: Path
    count: int


def query_summary(query,current_user_id=None):
    sorts={'-id':'Newest created','id':'Oldest created','-audit_date':'Audit date: newest first','audit_date':'Audit date: oldest first'}
    auditor=('All auditors' if query.audited_by_user_id is None else
             'My audits' if query.audited_by_user_id==current_user_id else 'Selected auditor')
    return '\n'.join((f'Driver search: {query.driver_name or "Any"}',f'Plate search: {query.plate_number or "Any"}',
        f'Station: {query.station or "All stations"}',f'Dates: {query.date_from or "Any start"} to {query.date_to or "Any end"}',
        f'Auditor: {auditor}',f'Order: {sorts[query.sort]}',f'Archived records: {"Included" if query.include_deleted else "Excluded"}'))


def export_audits(client,token,query,destination,control,progress,limits=Limits()):
    """All-or-nothing export; ApiError status survives for session handling."""
    started=datetime.now(timezone.utc);clock=time.monotonic();work=None
    count=payload=0;seen=set();previous=None;total=None
    def check():
        control.check()
        if time.monotonic()-clock>=limits.seconds:
            raise ExportError('Export time limit reached. Narrow the filters and retry.')
        # Finalization duplicates row XML and builds the ZIP while XML still
        # exists. Reserve 3x measured bytes plus 1 MiB per copy for buffered last
        # rows, workbook metadata and ZIP framing; fail before entering close.
        if work and 3*(sum(p.stat().st_size for p in work.iterdir() if p.is_file())+1024*1024)>limits.workspace:
            raise ExportError('Export temporary-file limit reached. Narrow the filters and retry.')
    try:
        check()
        work=Path(tempfile.mkdtemp(prefix='.dams-export-',dir=destination.path.parent))
        output=work/'report.xlsx'
        with xlsxwriter.Workbook(output,{'constant_memory':True,'tmpdir':str(work),
                'strings_to_formulas':False,'strings_to_urls':False,'strings_to_numbers':False}) as book:
            sheet=book.add_worksheet('Audits')
            heading=book.add_format({'bold':True,'bg_color':'#142D4E','font_color':'#FFFFFF','text_wrap':True})
            text=book.add_format({'num_format':'@','valign':'top'})
            remarks=book.add_format({'num_format':'@','text_wrap':True,'valign':'top'})
            sheet.freeze_panes(1,0);sheet.set_row(0,30)
            for col,width in enumerate((25,25,14,24,19,65,27,13,13)):
                sheet.set_column(col,col,width)
                sheet.write_string(0,col,HEADERS[col],heading)
            page_number=1
            while True:
                check()
                if page_number>limits.pages:raise ExportError('Export page limit reached. Narrow the filters and retry.')
                page=client.list_audits(token,replace(query,page=page_number,page_size=100))
                check()
                if total is None:
                    total=page.total
                    if total>limits.rows:raise ExportError('Export record limit reached. Narrow the filters and retry.')
                if (page.total!=total or page.page!=page_number or page.page_size!=100 or
                    len(page.items)!=min(100,total-count)):
                    raise ExportError('Audit results changed during export. Refresh and retry when editing has stopped.')
                for record in page.items:
                    check()
                    key=(record.audit_date,record.id) if 'audit_date' in query.sort else (record.id,)
                    if (record.id in seen or (record.deleted_at and not query.include_deleted) or
                        previous is not None and (key>=previous if query.sort.startswith('-') else key<=previous)):
                        raise ExportError('Audit ordering or membership changed during export. Refresh and retry.')
                    seen.add(record.id);previous=key
                    values=(record.driver_name,record.helper_name or '',record.audit_date,record.station,
                            record.plate_number,record.remarks or '',record.audited_by_name,str(record.id),
                            'Archived' if record.deleted_at else 'Active')
                    payload+=sum(len(value.encode('utf-8')) for value in values)
                    if payload>limits.payload or count>=limits.rows:
                        raise ExportError('Export data limit reached. Narrow the filters and retry.')
                    count+=1
                    for col,value in enumerate(values):
                        if sheet.write_string(count,col,value,remarks if col==5 else text)!=0:
                            raise ExportError('A value could not be exported completely. No report was saved.')
                    sheet.set_row(count,45 if '\n' in values[5] or len(values[5])>80 else 21)
                progress((count,'Fetching audits'))
                if count==total:break
                page_number+=1
            sheet.autofilter(0,0,max(1,count),len(HEADERS)-1)
            info=book.add_worksheet('Report information');info.set_column(0,0,24);info.set_column(1,1,100)
            for index,(name,value) in enumerate((('Generated from UTC',started.isoformat()),
                    ('Generated through UTC',datetime.now(timezone.utc).isoformat()),('Records exported',str(count)),
                    ('Filters and sort',query_summary(query)),('Consistency',CAVEAT),
                    ('Security','Unencrypted local report. Store in an appropriately protected location.'))):
                info.write_string(index,0,name,heading);info.write_string(index,1,value,remarks)
                info.set_row(index,75 if index in (3,4) else 32)
            check();progress((count,'Finalizing workbook'))
        check()
        if count:
            # Ensure bytes reach the filesystem before exposing the final name.
            with output.open('r+b') as stream:os.fsync(stream.fileno())
            control.commit(output,destination,clock+limits.seconds)
        return ExportResult(destination.path,count)
    except (ApiError,ExportError):raise
    except Exception:
        raise ExportError('Export could not be saved. Check the folder, free space and whether the file is open, then retry.') from None
    finally:
        if work:
            active=sys.exception()
            try:shutil.rmtree(work)
            except OSError:
                message='Export temporary files could not be removed. Inspect the .dams-export- folder in the selected destination; a complete report may already have been saved.'
                if isinstance(active,ApiError):raise ApiError(active.status,message=str(active)+' '+message) from None
                raise ExportError(message) from None
