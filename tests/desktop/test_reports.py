from dataclasses import replace
from pathlib import Path
from threading import Event,Thread
import zipfile
import xml.etree.ElementTree as ET

import pytest

from desktop import reports
from desktop.api import ApiError
from desktop.models import Audit, AuditPage, AuditQuery
from tests.desktop.test_api import AUDIT

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


class Client:
    def __init__(self, rows): self.rows=rows; self.calls=[]
    def list_audits(self, token, query):
        self.calls.append(query)
        return AuditPage(tuple(self.rows[(query.page-1)*100:query.page*100]),len(self.rows),query.page,100)


def row(id=1, **values): return Audit.parse(dict(AUDIT,id=id,**values),allow_deleted=True)


def run(tmp_path, rows=None, query=None, **kwargs):
    path=tmp_path/'report.xlsx'
    result=reports.export_audits(Client(rows or [row()]),'secret-token',query or AuditQuery(),
        reports.Destination.capture(path),reports.ExportControl(),lambda value:None,**kwargs)
    return path,result


def cells(path, sheet=1):
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read(f'xl/worksheets/sheet{sheet}.xml'))
    return root, [[(''.join(c.itertext()) if c.find('s:is',NS) is None else ''.join(c.find('s:is',NS).itertext()))
                   for c in r.findall('s:c',NS)] for r in root.findall('s:sheetData/s:row',NS)]


def test_workbook_fields_text_types_unicode_and_long_remarks(tmp_path):
    text='José 李\n'+('x'*9993)
    path,result=run(tmp_path,[row(driver_name='=1+1',plate_number='000001',remarks=text,helper_name=None)])
    root,values=cells(path)
    assert values[0]==list(reports.HEADERS)
    assert values[1]==['=1+1','','2026-10-26','Example Station','000001',text,'Original Reviewer','1','Active']
    assert all(c.get('t')=='inlineStr' for c in root.findall('.//s:sheetData/s:row/s:c',NS))
    assert not root.findall('.//s:f',NS) and not root.findall('.//s:hyperlink',NS)
    assert root.find('s:sheetViews/s:sheetView/s:pane',NS).get('ySplit')=='1'
    assert root.find('s:autoFilter',NS) is not None
    assert result.count==1
    assert 'secret-token' not in repr(result)


@pytest.mark.parametrize('text',['+cmd','-1+1','@SUM(A1:A2)','\t=1+1','https://example.com','bad\x00text','_x0000_'])
def test_untrusted_values_remain_literal_text(tmp_path,text):
    path,_=run(tmp_path,[row(driver_name=text)])
    root,_=cells(path)
    assert not root.findall('.//s:f',NS) and not root.findall('.//s:hyperlink',NS)


@pytest.mark.parametrize('sort',['id','-id','audit_date','-audit_date'])
def test_all_pages_and_applied_filters_preserved(tmp_path,sort):
    rows=[row(i) for i in range(1,206)]
    if sort.startswith('-'): rows.reverse()
    client=Client(rows)
    query=AuditQuery(page=3,page_size=25,sort=sort,driver_name='Driver',plate_number='0',station='Station',
                     date_from='2026-01-01',date_to='2026-12-31',audited_by_user_id=2,include_deleted=True)
    result=reports.export_audits(client,'token',query,reports.Destination.capture(tmp_path/'all.xlsx'),reports.ExportControl(),lambda p:None)
    assert result.count==205 and [q.page for q in client.calls]==[1,2,3]
    assert all(replace(q,page=3,page_size=25)==query for q in client.calls)


def test_archived_status_and_original_attribution(tmp_path):
    path,_=run(tmp_path,[row(deleted_at='2026-10-27T00:00:00Z')],AuditQuery(include_deleted=True))
    assert cells(path)[1][1][-1]=='Archived'


@pytest.mark.parametrize('fault',['duplicate','total','page','short','sort','archived'])
def test_detected_inconsistency_never_publishes(tmp_path,fault):
    rows=[row(i) for i in range(201,0,-1)]
    client=Client(rows); original=client.list_audits
    def fetch(token,q):
        p=original(token,q)
        if fault=='archived': return replace(p,items=(row(201,deleted_at='2026-10-27T00:00:00Z'),)+p.items[1:])
        if q.page==2:
            if fault=='duplicate': return replace(p,items=(rows[0],)+p.items[1:])
            if fault=='total': return replace(p,total=200)
            if fault=='page': return replace(p,page=1)
            if fault=='short': return replace(p,items=p.items[:-1])
            if fault=='sort': return replace(p,items=tuple(reversed(p.items)))
        return p
    client.list_audits=fetch
    with pytest.raises(reports.ExportError):
        reports.export_audits(client,'t',AuditQuery(),reports.Destination.capture(tmp_path/'x.xlsx'),reports.ExportControl(),lambda p:None)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('limit,value',[('rows',1),('pages',1),('payload',1),('workspace',1),('seconds',0)])
def test_resource_limits_do_not_truncate(tmp_path,limit,value):
    with pytest.raises(reports.ExportError):
        run(tmp_path,[row(i) for i in range(101,0,-1)] if limit=='pages' else [row(2),row(1)],
            limits=replace(reports.Limits(),**{limit:value}))
    assert not list(tmp_path.iterdir())


def test_cancel_before_and_during_export_preserves_existing_file(tmp_path):
    path=tmp_path/'x.xlsx';path.write_bytes(b'old')
    control=reports.ExportControl()
    def progress(p): control.cancel()
    with pytest.raises(reports.ExportError,match='cancel'):
        reports.export_audits(Client([row()]),'t',AuditQuery(),reports.Destination.capture(path),control,progress)
    assert path.read_bytes()==b'old' and len(list(tmp_path.iterdir()))==1


@pytest.mark.parametrize('status',[401,403,500,0])
def test_api_errors_preserved_without_partial_report(tmp_path,status):
    client=Client([])
    def fail(*args):raise ApiError(status)
    client.list_audits=fail
    with pytest.raises(ApiError) as error:
        reports.export_audits(client,'t',AuditQuery(),reports.Destination.capture(tmp_path/'x.xlsx'),reports.ExportControl(),lambda p:None)
    assert error.value.status==status and not list(tmp_path.iterdir())


def test_destination_changed_after_confirmation_is_not_replaced(tmp_path):
    path=tmp_path/'x.xlsx';path.write_bytes(b'old');dest=reports.Destination.capture(path)
    def progress(p):path.write_bytes(b'new external file')
    with pytest.raises(reports.ExportError,match='destination'):
        reports.export_audits(Client([row()]),'t',AuditQuery(),dest,reports.ExportControl(),progress)
    assert path.read_bytes()==b'new external file'


@pytest.mark.parametrize('name',['x.csv','CON.xlsx','bad:name.xlsx','x.xlsx.','NUL.xlsx'])
def test_invalid_destinations(tmp_path,name):
    with pytest.raises(reports.ExportError):reports.Destination.capture(tmp_path/name)


def test_disk_publication_failure_preserves_destination(tmp_path,monkeypatch):
    path=tmp_path/'x.xlsx';path.write_bytes(b'old')
    def fail(*args):raise PermissionError('sensitive-system-details')
    monkeypatch.setattr(reports,'publish',fail)
    with pytest.raises(reports.ExportError) as error:
        reports.export_audits(Client([row()]),'t',AuditQuery(),reports.Destination.capture(path),reports.ExportControl(),lambda p:None)
    assert 'sensitive-system-details' not in str(error.value) and path.read_bytes()==b'old'


def test_zero_records_no_workbook(tmp_path):
    result=reports.export_audits(Client([]),'t',AuditQuery(),reports.Destination.capture(tmp_path/'x.xlsx'),reports.ExportControl(),lambda p:None)
    assert result.count==0 and not list(tmp_path.iterdir())


def test_successful_publication_and_cancel_after_commit(tmp_path):
    path=tmp_path/'x.xlsx';control=reports.ExportControl()
    result=reports.export_audits(Client([row()]),'t',AuditQuery(),reports.Destination.capture(path),control,lambda p:None)
    control.cancel();control.check()
    assert zipfile.is_zipfile(path) and result.count==1 and control.published


def test_existing_workbook_is_never_replaced(tmp_path):
    path=tmp_path/'x.xlsx';path.write_bytes(b'old')
    with pytest.raises(reports.ExportError,match='new file'):
        reports.export_audits(Client([row()]),'t',AuditQuery(),reports.Destination.capture(path),reports.ExportControl(),lambda p:None)
    assert path.read_bytes()==b'old'


def test_cleanup_failure_preserves_401_status(tmp_path,monkeypatch):
    original=reports.shutil.rmtree;remaining=[];client=Client([])
    def fail(path):remaining.append(path);raise OSError()
    def denied(*args):raise ApiError(401)
    client.list_audits=denied;monkeypatch.setattr(reports.shutil,'rmtree',fail)
    try:
        with pytest.raises(ApiError) as e:
            reports.export_audits(client,'t',AuditQuery(),reports.Destination.capture(tmp_path/'x.xlsx'),reports.ExportControl(),lambda p:None)
        assert e.value.status==401 and 'temporary' in str(e.value)
    finally:
        for path in remaining:original(path)


def test_cancel_at_finalization_never_publishes(tmp_path):
    control=reports.ExportControl()
    def progress(p):
        if p[1]=='Finalizing workbook':control.cancel()
    with pytest.raises(reports.ExportError,match='cancel'):
        reports.export_audits(Client([row()]),'t',AuditQuery(),reports.Destination.capture(tmp_path/'x.xlsx'),control,progress)
    assert not list(tmp_path.iterdir())


def test_expired_session_blocks_final_publication(tmp_path):
    control=reports.ExportControl()
    def progress(p):control.deadline=0
    with pytest.raises(ApiError) as e:
        reports.export_audits(Client([row()]),'t',AuditQuery(),reports.Destination.capture(tmp_path/'x.xlsx'),control,progress)
    assert e.value.status==401 and not list(tmp_path.iterdir())


def test_workbook_close_failure_preserves_old_file(tmp_path,monkeypatch):
    path=tmp_path/'x.xlsx';path.write_bytes(b'old')
    original=reports.xlsxwriter.Workbook.close
    def fail(book):original(book);raise OSError('private details')
    monkeypatch.setattr(reports.xlsxwriter.Workbook,'close',fail)
    with pytest.raises(reports.ExportError) as e:
        reports.export_audits(Client([row()]),'t',AuditQuery(),reports.Destination.capture(path),reports.ExportControl(),lambda p:None)
    assert 'private details' not in str(e.value) and path.read_bytes()==b'old'


def test_cleanup_failure_is_disclosed(tmp_path,monkeypatch):
    original=reports.shutil.rmtree;remaining=[]
    def fail(path):remaining.append(path);raise OSError()
    monkeypatch.setattr(reports.shutil,'rmtree',fail)
    try:
        with pytest.raises(reports.ExportError,match='could not be removed'):run(tmp_path)
    finally:
        for path in remaining:original(path)


def test_readable_metadata_contains_no_token(tmp_path):
    path,_=run(tmp_path)
    _,values=cells(path,2)
    assert any('offset pagination' in cell for line in values for cell in line)
    with zipfile.ZipFile(path) as z:
        assert not any(b'secret-token' in z.read(name) for name in z.namelist())


def test_workspace_budget_reserves_finalization_headroom(tmp_path):
    rows=[row(i,remarks='x'*10000) for i in range(80,0,-1)]
    with pytest.raises(reports.ExportError,match='temporary-file'):
        run(tmp_path,rows,limits=replace(reports.Limits(),workspace=1_200_000))
    assert not list(tmp_path.iterdir())


def test_elapsed_deadline_is_rechecked_after_disk_flush(tmp_path,monkeypatch):
    clock=[0.0];monkeypatch.setattr(reports.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(reports.os,'fsync',lambda fd:clock.__setitem__(0,601))
    with pytest.raises(reports.ExportError,match='time limit'):run(tmp_path)
    assert not list(tmp_path.iterdir())


def test_racing_new_destination_is_not_clobbered(tmp_path,monkeypatch):
    link=reports.os.link;path=tmp_path/'report.xlsx'
    def collide(source,target):
        target.write_bytes(b'external workbook');link(source,target)
    monkeypatch.setattr(reports.os,'link',collide)
    with pytest.raises(reports.ExportError):run(tmp_path)
    assert path.read_bytes()==b'external workbook'


def test_large_export_completes_without_truncation(tmp_path):
    path,result=run(tmp_path,[row(i) for i in range(20_000,0,-1)])
    assert result.count==20_000 and len(cells(path)[1])==20_001


def test_filter_summary_uses_hr_labels():
    summary=reports.query_summary(AuditQuery(audited_by_user_id=2,include_deleted=True,sort='-audit_date'),2)
    assert 'Auditor: My audits' in summary and 'Archived records: Included' in summary
    assert 'Audit date: newest first' in summary and 'audited_by_user_id' not in summary


def test_cancellation_never_blocks_ui_during_publication(tmp_path,monkeypatch):
    entered=Event();release=Event();cancelled=Event();control=reports.ExportControl()
    source=tmp_path/'source';source.write_bytes(b'completed workbook')
    destination=reports.Destination.capture(tmp_path/'report.xlsx')
    original=reports.os.link
    def slow_link(*args):entered.set();release.wait(4);original(*args)
    monkeypatch.setattr(reports.os,'link',slow_link)
    writer=Thread(target=lambda:control.commit(source,destination));writer.start()
    assert entered.wait(2)
    canceller=Thread(target=lambda:(control.cancel(),cancelled.set()));canceller.start()
    try:assert cancelled.wait(.3),'UI cancellation waited for disk publication'
    finally:release.set();writer.join(3);canceller.join(3)
    assert control.published and destination.path.read_bytes()==source.read_bytes()
    control.check()
