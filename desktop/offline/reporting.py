"""Bounded point-in-time local reports, independent of Tk and online clients.

The repository adapter is used only on its owner thread. Formatting starts after
the read transaction has committed; no SQLite handle escapes in a snapshot.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import zipfile

import xlsxwriter

from .models import AuditFilter, OfflineError, invalid_input, normalize_text, valid_date
from .repository import _SORTS, _audit, _paging


@dataclass(frozen=True)
class ReportLimits:
    rows: int = 20_000
    text: int = 100 * 1024 * 1024
    workspace: int = 256 * 1024 * 1024
    seconds: float = 600


class _Budget:
    def __init__(self, limits, cancel):
        ceilings = ReportLimits()
        for name in ('rows', 'text', 'workspace', 'seconds'):
            value = getattr(limits, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= getattr(ceilings, name):
                invalid_input()
        self.limits, self.cancel = limits, cancel
        self.deadline = time.monotonic() + limits.seconds

    def check(self, work=None, *, reserve=0):
        if self.cancel():
            raise OfflineError('cancelled', 'Report cancelled before publication. No report was saved.')
        if time.monotonic() >= self.deadline:
            raise OfflineError('limit', 'Report time limit reached. Narrow the filters and retry.')
        if work is not None:
            size = sum(item.stat().st_size for item in work.iterdir() if item.is_file())
            if size + reserve > self.limits.workspace:
                raise OfflineError('limit', 'Report temporary workspace limit reached. Narrow the filters and retry.')
            if reserve > shutil.disk_usage(work).free:
                raise OfflineError('file', 'Insufficient temporary disk space. No report was saved.')


@dataclass(frozen=True)
class ReportSnapshot:
    rows: tuple
    total: int
    active: int
    archived: int
    snapshot_utc: str
    applied_filter: AuditFilter
    ordering: str


def report_snapshot(repo, filter, *, cancel=lambda: False, progress=lambda value: None,
                    limits=ReportLimits(), _budget=None):
    """Capture every match with the list's predicates in one owner transaction."""
    budget = _budget or _Budget(limits, cancel)
    budget.check()
    with repo._transaction():
        if not isinstance(filter, AuditFilter):
            invalid_input()
        _paging(filter.page, filter.page_size)
        if not isinstance(filter.sort, str) or filter.sort not in _SORTS or type(filter.include_archived) is not bool:
            invalid_input()
        if any(value is not None and not valid_date(value) for value in (filter.date_from, filter.date_to)):
            invalid_input()
        if filter.date_from and filter.date_to and filter.date_from > filter.date_to:
            invalid_input()
        clauses = [] if filter.include_archived else ['archived_at IS NULL']
        args = []
        normalized = {}
        for field, name in (('driver_name', 'driver'), ('plate_number', 'plate'), ('station', 'station')):
            text = normalize_text(getattr(filter, name), 200, optional=True)
            normalized[name] = text
            if text:
                clauses.append(f"{field} LIKE ? ESCAPE '\\'")
                args.append('%' + text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        for operator, value in (('>=', filter.date_from), ('<=', filter.date_to)):
            if value is not None:
                clauses.append(f'audit_date {operator} ?')
                args.append(value)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        total = repo._connection.execute('SELECT count(*) FROM audit_records' + where, args).fetchone()[0]
        if total > budget.limits.rows:
            raise OfflineError('limit', 'Report record limit reached. Narrow the filters and retry.')
        stamp = datetime.now(timezone.utc).isoformat()
        progress((0, 'Reading local snapshot'))
        rows = []
        payload = 0
        for row in repo._connection.execute('SELECT * FROM audit_records' + where + ' ORDER BY ' + _SORTS[filter.sort], args):
            budget.check()
            record = _audit(row)
            try:
                payload += sum(len(value.encode('utf-8')) for value in _row_values(record))
            except UnicodeError:
                raise OfflineError('report', 'An audit contains unsupported text. No report was saved.') from None
            if payload > budget.limits.text or len(rows) >= budget.limits.rows:
                raise OfflineError('limit', 'Report text or record limit reached. Narrow the filters and retry.')
            rows.append(record)
            if len(rows) == 1 or len(rows) % 100 == 0:
                progress((len(rows), 'Reading local snapshot'))
        budget.check()
        if len(rows) != total:
            raise OfflineError('report', 'The local snapshot could not be read completely. No report was saved.')
        archived = sum(item.archived for item in rows)
        return ReportSnapshot(tuple(rows), total, total - archived, archived, stamp,
                              replace(filter, **normalized, page=1, page_size=25), _SORTS[filter.sort])


HEADERS = ('Driver Name', 'Helper Name', 'Audit Date', 'Station', 'Plate Number',
           'Remarks', 'Audited By', 'Record ID', 'Status')


@dataclass(frozen=True)
class ReportResult:
    path: Path
    count: int
    cleanup_warning: str = ''


def _row_values(record):
    return (record.driver_name, record.helper_name or '', record.audit_date,
            record.station, record.plate_number, record.remarks or '',
            record.audited_by_name, record.id, 'Archived' if record.archived else 'Active')


def filter_summary(snapshot):
    f = snapshot.applied_filter
    return '\n'.join((f'Driver search: {f.driver or "Any"}', f'Plate search: {f.plate or "Any"}',
                      f'Station search: {f.station or "Any"}',
                      f'Inclusive dates: {f.date_from or "Any start"} to {f.date_to or "Any end"}',
                      f'Include archived: {"Yes" if f.include_archived else "No"}',
                      f'Ordering: {f.sort}; {snapshot.ordering}'))


class _Output:
    """Bound ZIP writes while XlsxWriter's XML stages still occupy the workspace."""
    def __init__(self, stream, work, budget):
        self.stream, self.work, self.budget = stream, work, budget
        self.failure = None
        self.position = 0

    def write(self, raw):
        if self.failure is None:
            try:
                self.budget.check(self.work, reserve=len(raw))
                return self.stream.write(raw)
            except (OfflineError, OSError) as error:
                # XlsxWriter 3.3.0 does not close its ZIP on arbitrary write
                # exceptions. Drain its finalization into a counting sink after
                # the first budget failure; never grow the stage or publish it.
                self.failure = (OfflineError(error.code, error.message) if isinstance(error, OfflineError)
                                else OfflineError('file', 'The workbook could not be written. Check free disk space and folder access.'))
                self.position = self.stream.tell()
        if self.failure is not None:
            self.position += len(raw)
            return len(raw)

    def tell(self):
        return self.position if self.failure is not None else self.stream.tell()

    def seek(self, offset, whence=0):
        if self.failure is not None:
            self.position = offset if whence == 0 else self.position + offset
            return self.position
        return self.stream.seek(offset, whence)

    def flush(self):
        return self.stream.flush()


def _destination(path):
    target = Path(path).absolute()
    name = target.name
    if (target.suffix.lower() != '.xlsx' or name.endswith((' ', '.')) or
            re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or
            re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I) or
            not target.parent.is_dir()):
        raise OfflineError('file', 'Choose a valid new .xlsx filename in an existing folder.')
    if os.path.lexists(target):
        raise OfflineError('exists', 'This destination already exists. Choose a new filename; it was not replaced.')
    return target


def export_report(repo, filter, path, *, cancel=lambda: False, progress=lambda value: None,
                  limits=ReportLimits()):
    """Create, flush and validate a workbook before publishing its new name."""
    work = None
    published = False
    result = None
    try:
        budget = _Budget(limits, cancel)
        budget.check()
        target = _destination(path)
        snapshot = report_snapshot(repo, filter, progress=progress, _budget=budget)
        budget.check()
        work = Path(tempfile.mkdtemp(prefix='.bhli-report-', dir=target.parent))
        output = work / 'report.xlsx'
        with output.open('w+b') as stream:
            sink = _Output(stream, work, budget)
            _write_workbook(snapshot, sink, work, budget, progress)
            if sink.failure is not None:
                raise sink.failure
        budget.check(work)
        with output.open('r+b') as stream:
            os.fsync(stream.fileno())
        with zipfile.ZipFile(output) as archive:
            for item in archive.infolist():
                with archive.open(item) as member:
                    while member.read(64 * 1024):
                        budget.check(work)
        budget.check(work)
        if os.name == 'nt':
            os.rename(output, target)
        else:
            os.link(output, target)
        published = True
        result = ReportResult(target, snapshot.total)
    except OfflineError:
        raise
    except FileExistsError:
        raise OfflineError('exists', 'The destination now exists. Choose a new filename; it was not replaced.') from None
    except Exception:
        raise OfflineError('file', 'The report could not be saved. Check disk space and folder access, then retry.') from None
    finally:
        if work is not None:
            active = sys.exception()
            try:
                shutil.rmtree(work)
            except OSError:
                warning = f'Owned temporary report files could not be removed: {work}'
                if published:
                    result = replace(result, cleanup_warning=warning)
                else:
                    raise OfflineError(getattr(active, 'code', 'file'), str(active or 'No report was saved.') + ' ' + warning) from None
    return result


def _write_workbook(snapshot, sink, work, budget, progress):
    with xlsxwriter.Workbook(sink, {'constant_memory': True, 'tmpdir': str(work),
            'strings_to_formulas': False, 'strings_to_urls': False, 'strings_to_numbers': False}) as book:
        sheet = book.add_worksheet('Audits')
        heading = book.add_format({'bold': True, 'bg_color': '#142D4E', 'font_color': '#FFFFFF', 'text_wrap': True})
        text = book.add_format({'num_format': '@', 'valign': 'top'})
        wrapped = book.add_format({'num_format': '@', 'text_wrap': True, 'valign': 'top'})
        sheet.freeze_panes(1, 0)
        sheet.set_row(0, 30)
        for col, width in enumerate((25, 25, 14, 24, 19, 65, 27, 38, 13)):
            sheet.set_column(col, col, width)
            sheet.write_string(0, col, HEADERS[col], heading)
        for index, record in enumerate(snapshot.rows, 1):
            budget.check(work)
            for col, value in enumerate(_row_values(record)):
                if sheet.write_string(index, col, value, wrapped if col == 5 else text) != 0:
                    raise OfflineError('report', 'A value could not be written completely. No report was saved.')
            sheet.set_row(index, 45 if record.remarks and (len(record.remarks) > 80 or '\n' in record.remarks) else 21)
            progress((index, 'Writing workbook'))
        sheet.autofilter(0, 0, max(1, snapshot.total), 8)
        info = book.add_worksheet('Report information')
        info.set_column(0, 0, 25)
        info.set_column(1, 1, 100)
        details = (('Generated UTC', datetime.now(timezone.utc).isoformat()),
                   ('Snapshot UTC', snapshot.snapshot_utc), ('Filters and ordering', filter_summary(snapshot)),
                   ('Records exported', str(snapshot.total)), ('Active', str(snapshot.active)),
                   ('Archived', str(snapshot.archived)), ('Consistency', 'point-in-time local snapshot'),
                   ('Edition', 'BHLI Audit Offline'),
                   ('Security', 'Unencrypted local report. Store in an appropriately protected location.'),
                   ('Result', 'No matching audits (zero records).' if not snapshot.total else 'Complete matching result.'))
        for index, (name, value) in enumerate(details):
            info.write_string(index, 0, name, heading)
            if info.write_string(index, 1, value, wrapped) != 0:
                raise OfflineError('report', 'Report information could not be written completely.')
            info.set_row(index, 120 if index == 2 else 36)
        budget.check(work)
        # Finalization temporarily duplicates XML before adding the ZIP.
        # Reserve conservatively for buffered rows, metadata and framing.
        used = sum(item.stat().st_size for item in work.iterdir() if item.is_file())
        budget.check(work, reserve=2 * used + 1024 * 1024)
        progress((snapshot.total, 'Finalizing workbook'))
        budget.check(work)
