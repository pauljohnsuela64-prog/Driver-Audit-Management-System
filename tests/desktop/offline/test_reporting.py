"""Fictional SQLite snapshots and actual workbook readback at the report seam."""
from dataclasses import replace
import zipfile
from xml.etree import ElementTree as ET

import pytest

from desktop.offline.models import AuditFilter, OfflineError, new_uuid
from desktop.offline.repository import SqliteRepository
from desktop.offline.reporting import report_snapshot


VALUES = dict(driver_name='Fictional Driver', helper_name=None, audit_date='2026-11-06',
              station='Test Station', plate_number='00123', remarks='Unicode 日本語 😀\n=SUM(A1)')


@pytest.fixture
def repo(tmp_path):
    store = SqliteRepository(tmp_path / 'fictional.db')
    store.save_profile('Original Auditor')
    yield store
    store.close()


def test_snapshot_exports_all_matches_and_original_attribution(repo):
    records = [repo.create(new_uuid(), VALUES) for _ in range(30)]
    repo.archive(records[-1].id, 1)
    repo.save_profile('Renamed Auditor')
    result = report_snapshot(repo, AuditFilter(page=2, page_size=1, sort='audit_date'))
    assert result.total == 29
    assert result.active == 29 and result.archived == 0
    assert [item.id for item in result.rows] == [item.id for item in records[:-1]]
    assert {item.audited_by_name for item in result.rows} == {'Original Auditor'}
    assert result.applied_filter.page == 1
    assert report_snapshot(repo, AuditFilter(include_archived=True)).archived == 1


def test_workbook_has_exact_columns_literal_cells_and_two_sheets(repo, tmp_path):
    from desktop.offline.reporting import export_report
    repo.create(new_uuid(), dict(VALUES, driver_name='=2+2', helper_name='+123',
                                station='https://example.invalid', remarks='\x01日本語 😀\n@literal'))
    path = tmp_path / 'report.xlsx'
    result = export_report(repo, AuditFilter(), path)
    assert result.count == 1 and result.path == path
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        assert [sheet.attrib['name'] for sheet in book.findall('s:sheets/s:sheet', ns)] == ['Audits', 'Report information']
        xml = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = xml.findall('s:sheetData/s:row', ns)
        texts = lambda row: [''.join(cell.itertext()) for cell in row]
        assert texts(rows[0]) == ['Driver Name', 'Helper Name', 'Audit Date', 'Station', 'Plate Number', 'Remarks', 'Audited By', 'Record ID', 'Status']
        assert texts(rows[1])[:7] == ['=2+2', '+123', '2026-11-06', 'https://example.invalid', '00123', '_x0001_日本語 😀\n@literal', 'Original Auditor']
        assert all(cell.attrib.get('t') == 'inlineStr' for cell in rows[1])
        assert not xml.findall('.//s:f', ns) and not xml.findall('.//s:hyperlink', ns)
        assert not any('externalLink' in name or 'vba' in name.lower() for name in archive.namelist())
        info = archive.read('xl/worksheets/sheet2.xml').decode()
        assert 'point-in-time local snapshot' in info
        assert 'Unencrypted' in info


def test_empty_report_is_a_real_zero_record_workbook(repo, tmp_path):
    from desktop.offline.reporting import export_report
    path = tmp_path / 'empty.xlsx'
    result = export_report(repo, AuditFilter(), path)
    assert result.count == 0 and path.is_file()
    with zipfile.ZipFile(path) as archive:
        assert b'No matching audits' in archive.read('xl/worksheets/sheet2.xml')


@pytest.mark.parametrize('limit,value', [('rows', 1), ('text', 10), ('workspace', 100), ('seconds', 0.000001)])
def test_limits_refuse_complete_publication(repo, tmp_path, limit, value):
    from desktop.offline.reporting import export_report, ReportLimits
    repo.create(new_uuid(), VALUES)
    repo.create(new_uuid(), VALUES)
    path = tmp_path / 'bounded.xlsx'
    with pytest.raises(OfflineError) as caught:
        export_report(repo, AuditFilter(), path, limits=replace(ReportLimits(), **{limit: value}))
    assert caught.value.code == 'limit'
    assert not path.exists() and not list(tmp_path.glob('.bhli-report-*'))


def test_existing_destination_and_race_are_never_overwritten(repo, tmp_path):
    from desktop.offline.reporting import export_report
    repo.create(new_uuid(), VALUES)
    path = tmp_path / 'existing.xlsx'
    path.write_bytes(b'Original')
    with pytest.raises(OfflineError) as caught:
        export_report(repo, AuditFilter(), path)
    assert caught.value.code == 'exists' and path.read_bytes() == b'Original'
    path.unlink()
    def race(value):
        if value[1] == 'Finalizing workbook':
            path.write_bytes(b'Racing destination')
    with pytest.raises(OfflineError) as caught:
        export_report(repo, AuditFilter(), path, progress=race)
    assert caught.value.code == 'exists' and path.read_bytes() == b'Racing destination'
    assert not list(tmp_path.glob('.bhli-report-*'))


@pytest.mark.parametrize('phase', ['Reading local snapshot', 'Writing workbook', 'Finalizing workbook'])
def test_cancel_at_each_prepublication_phase_never_publishes(repo, tmp_path, phase):
    from desktop.offline.reporting import export_report
    from threading import Event
    repo.create(new_uuid(), VALUES)
    token = Event()
    def progress(value):
        if value[1] == phase:
            token.set()
    path = tmp_path / 'cancelled.xlsx'
    with pytest.raises(OfflineError) as caught:
        export_report(repo, AuditFilter(), path, cancel=token.is_set, progress=progress)
    assert caught.value.code == 'cancelled'
    assert not path.exists() and not list(tmp_path.glob('.bhli-report-*'))


def test_disk_fsync_failure_has_no_output_or_stage(repo, tmp_path, monkeypatch):
    from desktop.offline.reporting import export_report
    import os
    repo.create(new_uuid(), VALUES)
    def full(handle):
        raise OSError('fictional full disk')
    monkeypatch.setattr(os, 'fsync', full)
    with pytest.raises(OfflineError) as caught:
        export_report(repo, AuditFilter(), tmp_path / 'full.xlsx')
    assert caught.value.code == 'file'
    assert not list(tmp_path.glob('*.xlsx')) and not list(tmp_path.glob('.bhli-report-*'))


def test_snapshot_limits_also_apply_when_caller_only_prepares(repo):
    from desktop.offline.reporting import ReportLimits
    repo.create(new_uuid(), VALUES)
    with pytest.raises(OfflineError) as caught:
        report_snapshot(repo, AuditFilter(), limits=replace(ReportLimits(), text=1))
    assert caught.value.code == 'limit'


def test_one_read_snapshot_survives_concurrent_wal_change_between_count_and_rows(tmp_path):
    path = tmp_path / 'concurrent.db'
    repo = SqliteRepository(path)
    repo._connection.execute('PRAGMA journal_mode=WAL')
    repo.save_profile('Original Auditor')
    original = repo.create(new_uuid(), VALUES)
    second = SqliteRepository(path)
    def change(value):
        if value == (0, 'Reading local snapshot'):
            second.update(original.id, 1, dict(VALUES, remarks='Changed by second connection'))
            second.create(new_uuid(), VALUES)
    try:
        snapshot = report_snapshot(repo, AuditFilter(), progress=change)
        assert snapshot.total == 1 and len(snapshot.rows) == 1
        assert snapshot.rows[0].remarks == 'Unicode 日本語 😀\n=SUM(A1)'
        assert repo.list(AuditFilter()).total == 2
        assert repo.read(original.id).remarks == 'Changed by second connection'
    finally:
        second.close()
        repo.close()


@pytest.mark.parametrize('sort,expected', [('created', [0, 1, 2]), ('-created', [2, 1, 0]),
                                         ('audit_date', [1, 0, 2]), ('-audit_date', [2, 0, 1])])
def test_stable_order_uses_sequence_tiebreak(repo, sort, expected):
    records = [repo.create(new_uuid(), dict(VALUES, audit_date=day))
               for day in ('2026-11-06', '2026-11-05', '2026-11-06')]
    snapshot = report_snapshot(repo, AuditFilter(sort=sort))
    assert [item.id for item in snapshot.rows] == [records[index].id for index in expected]


def test_inclusive_dates_literal_wildcards_station_and_archive_match_applied_list(repo):
    kept = repo.create(new_uuid(), dict(VALUES, driver_name='100%_Fictional', station='Station%_One'))
    repo.create(new_uuid(), dict(VALUES, driver_name='100XYFictional', station='StationXYOne'))
    repo.create(new_uuid(), dict(VALUES, driver_name='100%_Fictional', station='Station%_One', audit_date='2026-11-05'))
    f = AuditFilter(driver='%_', station='%_', plate='001', date_from='2026-11-06', date_to='2026-11-06')
    assert [item.id for item in report_snapshot(repo, f).rows] == [kept.id]
    repo.archive(kept.id, 1)
    assert report_snapshot(repo, f).total == 0
    archived = report_snapshot(repo, replace(f, include_archived=True))
    assert archived.total == 1 and archived.active == 0 and archived.archived == 1


def test_long_multiline_remarks_preserved_and_optional_blanks_are_text(repo, tmp_path):
    from desktop.offline.reporting import export_report
    remarks = 'Long fictional remark\n' + '😀日本語' * 2000
    repo.create(new_uuid(), dict(VALUES, remarks=remarks))
    path = tmp_path / 'long.xlsx'
    export_report(repo, AuditFilter(), path)
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        xml = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        cells = {cell.attrib['r']: cell for cell in xml.findall('s:sheetData/s:row/s:c', ns)}
        assert ''.join(cells['F2'].itertext()) == remarks
        assert ''.join(cells['B2'].itertext()) == '' and cells['B2'].attrib['t'] == 'inlineStr'


def test_cleanup_failure_reports_owned_path_and_does_not_undo_completed_file(repo, tmp_path, monkeypatch):
    from desktop.offline.reporting import export_report
    import shutil
    repo.create(new_uuid(), VALUES)
    real = shutil.rmtree
    def refused(path):
        raise OSError('fictional cleanup denial')
    monkeypatch.setattr(shutil, 'rmtree', refused)
    path = tmp_path / 'saved.xlsx'
    result = export_report(repo, AuditFilter(), path)
    assert result.count == 1 and path.is_file()
    stages = list(tmp_path.glob('.bhli-report-*'))
    assert len(stages) == 1 and str(stages[0]) in result.cleanup_warning
    monkeypatch.setattr(shutil, 'rmtree', real)
    real(stages[0])


def test_late_cancel_after_atomic_publish_keeps_confirmed_file(repo, tmp_path, monkeypatch):
    from desktop.offline.reporting import export_report
    from threading import Event
    import os
    repo.create(new_uuid(), VALUES)
    token = Event()
    name = 'rename' if os.name == 'nt' else 'link'
    real = getattr(os, name)
    def publish_then_cancel(*args):
        real(*args)
        token.set()
    monkeypatch.setattr(os, name, publish_then_cancel)
    path = tmp_path / 'late.xlsx'
    result = export_report(repo, AuditFilter(), path, cancel=token.is_set)
    assert result.count == 1 and path.is_file()


def test_record_cap_boundary_accepts_complete_result(repo, tmp_path):
    from desktop.offline.reporting import export_report, ReportLimits
    repo.create(new_uuid(), VALUES)
    repo.create(new_uuid(), VALUES)
    assert export_report(repo, AuditFilter(), tmp_path / 'boundary.xlsx', limits=replace(ReportLimits(), rows=2)).count == 2


def test_wal_writer_changes_an_unread_record_mid_iteration_without_mixed_versions(tmp_path):
    path = tmp_path / 'mid-read.db'
    repo = SqliteRepository(path)
    repo._connection.execute('PRAGMA journal_mode=WAL')
    repo.save_profile('Fictional Auditor')
    originals = [repo.create(new_uuid(), dict(VALUES, remarks=f'Original {index}')) for index in range(3)]
    second = SqliteRepository(path)
    changed = False
    def change(value):
        nonlocal changed
        if value == (1, 'Reading local snapshot'):
            second.create(new_uuid(), VALUES)
            second.update(originals[2].id, 1, dict(VALUES, remarks='Changed unread record'))
            changed = True
    try:
        snapshot = report_snapshot(repo, AuditFilter(sort='created'), progress=change)
        assert changed
        assert snapshot.total == 3 and [row.remarks for row in snapshot.rows] == ['Original 0', 'Original 1', 'Original 2']
        fresh = report_snapshot(repo, AuditFilter(sort='created'))
        assert fresh.total == 4 and fresh.rows[2].remarks == 'Changed unread record'
    finally:
        second.close()
        repo.close()


@pytest.mark.parametrize('filter,expected', [
    (AuditFilter(driver='Driver one'), [0]),
    (AuditFilter(plate='001'), [0, 2]),
    (AuditFilter(station='South'), [1]),
    (AuditFilter(date_from='2026-11-05', date_to='2026-11-05'), [1]),
    (AuditFilter(date_from='2026-11-05', date_to='2026-11-06'), [0, 1]),
    (AuditFilter(include_archived=True), [0, 1, 2, 3]),
])
def test_individual_applied_filter_matrix(repo, filter, expected):
    records = [repo.create(new_uuid(), dict(VALUES, driver_name=driver, plate_number=plate, station=station, audit_date=day))
               for driver, plate, station, day in [
                   ('Driver one', '00123', 'North', '2026-11-06'),
                   ('Driver two', '00234', 'South', '2026-11-05'),
                   ('Driver three', '00199', 'North', '2026-11-04'),
                   ('Driver archived', '00345', 'East', '2026-11-03')]]
    repo.archive(records[3].id, 1)
    snapshot = report_snapshot(repo, replace(filter, sort='created'))
    assert [row.id for row in snapshot.rows] == [records[index].id for index in expected]


def test_zip_write_disk_full_is_clean_without_unraisable_finalizer(repo, tmp_path, monkeypatch):
    from desktop.offline.reporting import export_report
    from pathlib import Path
    repo.create(new_uuid(), VALUES)
    real_open = Path.open
    class FullOutput:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def write(self, raw):
            raise OSError('Fictional full output volume')
    def open_output(path, mode='r', *args, **kwargs):
        stream = real_open(path, mode, *args, **kwargs)
        return FullOutput(stream) if path.name == 'report.xlsx' and mode == 'w+b' else stream
    monkeypatch.setattr(Path, 'open', open_output)
    with pytest.raises(OfflineError) as caught:
        export_report(repo, AuditFilter(), tmp_path / 'full-write.xlsx')
    assert caught.value.code == 'file'
    assert not list(tmp_path.glob('.bhli-report-*')) and not (tmp_path / 'full-write.xlsx').exists()
