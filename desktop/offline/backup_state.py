"""Complete, platform-bound owned SQLite state; never a filtered transfer."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import sqlite3
from types import MappingProxyType

from .models import FIELDS, OfflineError, normalize_name, new_uuid, validate_uuid
from .repository import _audit, _timestamp
from .schema import V2, indexes, owned

MAX_BYTES = 64*1024*1024
MAX_LINE = 1024*1024
TABLES = ('app_meta','local_profile','auditor_identities','audit_records','audit_events','transfer_receipts')
CAPS = dict(zip(TABLES,(2,1,40001,20000,100000,20000)))
ORDERS = dict(zip(TABLES,('key','singleton','id','seq','audit_id,revision','package_id')))
APPS = {'windows':'com.bhli.audit.offline.windows','android':'com.bhli.audit.offline'}
MAX_INT = 2**63-1


def invalid():
    raise OfflineError('backup_state', 'This complete backup state is invalid, incompatible or exceeds safe limits. Nothing was restored.')


def _check(value, depth=0):
    if depth > 6: invalid()
    if value is None: return
    if type(value) is int:
        if not 0 <= value <= MAX_INT: invalid()
    elif isinstance(value,str):
        try: value.encode('utf-8',errors='strict')
        except UnicodeError: invalid()
    elif isinstance(value,dict):
        for key,item in value.items():
            if not isinstance(key,str) or not key.isascii(): invalid()
            _check(item,depth+1)
    elif isinstance(value,list):
        for item in value: _check(item,depth+1)
    else: invalid()


def canonical(value):
    _check(value)
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def _json(raw, *, exact=False):
    if not isinstance(raw,bytes) or len(raw)>MAX_LINE: invalid()
    depth=0; quoted=escaped=False
    for byte in raw:
        if quoted:
            if escaped: escaped=False
            elif byte==92: escaped=True
            elif byte==34: quoted=False
        elif byte==34: quoted=True
        elif byte in (91,123):
            depth+=1
            if depth>6: invalid()
        elif byte in (93,125): depth-=1
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: invalid()
            result[key]=value
        return result
    try:
        value=json.loads(raw.decode('utf-8',errors='strict'),object_pairs_hook=pairs,
                         parse_constant=lambda _:invalid(),parse_float=lambda _:invalid())
        _check(value)
        if exact and canonical(value)+b'\n'!=raw: invalid()
        return value
    except (ValueError,UnicodeError,RecursionError): invalid()


def _integer(value, minimum=0):
    if type(value) is not int or not minimum<=value<=MAX_INT: invalid()


def _time(value):
    if not isinstance(value,str): invalid()
    try:
        parsed=_timestamp(value)
        if not 1000<=parsed.year<=9999: invalid()
        return parsed
    except (ValueError,TypeError,OverflowError): invalid()


def _row_snapshot(value):
    keys=set(FIELDS)|{'id','profile_id','audited_by_name','created_at','updated_at','revision','archived_at'}
    if not isinstance(value,dict) or set(value)!=keys: invalid()
    parsed=_audit(value)
    if any(value[k]!=getattr(parsed,k) for k in (*FIELDS,'audited_by_name')): invalid()
    for key in ('created_at','updated_at','archived_at'):
        if value[key] is not None: _time(value[key])
    return parsed


def _validate(db, platform, sequence):
    meta=dict(db.execute('SELECT key,value FROM app_meta'))
    if len(meta)!=2 or meta.get('app_id')!=APPS[platform]: invalid()
    validate_uuid(meta.get('installation_id'))
    identities=set()
    for row in db.execute('SELECT id FROM auditor_identities'):
        validate_uuid(row['id']); identities.add(row['id'])
    for row in db.execute('SELECT * FROM local_profile'):
        if row['singleton']!=1 or row['id'] not in identities or normalize_name(row['name'])!=row['name']: invalid()
        validate_uuid(row['id'])
    maximum=0; seen_events=0
    for row in db.execute('SELECT * FROM audit_records ORDER BY seq'):
        current=dict(row); seq=current.pop('seq'); _integer(seq,1); maximum=max(maximum,seq)
        parsed=_row_snapshot(current)
        if parsed.profile_id not in identities: invalid()
        previous=None; revision=0
        for event in db.execute('SELECT * FROM audit_events WHERE audit_id=? ORDER BY revision',(parsed.id,)):
            revision+=1; seen_events+=1
            validate_uuid(event['id']); validate_uuid(event['actor_profile_id'])
            if event['actor_profile_id'] not in identities or normalize_name(event['actor_name'])!=event['actor_name']: invalid()
            before=None if event['before_json'] is None else _json(event['before_json'].encode('utf-8'))
            after=_json(event['after_json'].encode('utf-8')); after_parsed=_row_snapshot(after)
            if before!=previous or event['revision']!=revision or after['revision']!=revision or after['id']!=parsed.id: invalid()
            if _time(event['created_at'])!=after_parsed.updated_at: invalid()
            if previous is None:
                if (event['action']!='CREATE' or after['archived_at'] is not None or before is not None
                        or after_parsed.created_at!=after_parsed.updated_at or event['actor_profile_id']!=after['profile_id']
                        or event['actor_name']!=after['audited_by_name']): invalid()
            else:
                if previous['archived_at'] is not None or any(after[k]!=previous[k] for k in ('id','profile_id','audited_by_name','created_at')): invalid()
                changed=any(after[k]!=previous[k] for k in FIELDS)
                if event['action']=='UPDATE':
                    if not changed or after['archived_at'] is not None: invalid()
                elif event['action']=='ARCHIVE':
                    if changed or after['archived_at'] is None or _time(after['archived_at'])!=after_parsed.updated_at: invalid()
                else: invalid()
            previous=after
        if revision!=parsed.revision or _row_snapshot(previous)!=parsed: invalid()
    if db.execute('SELECT count(*) FROM audit_events').fetchone()[0]!=seen_events: invalid()
    if sequence is not None: _integer(sequence)
    if maximum and (sequence is None or sequence<maximum): invalid()
    for row in db.execute('SELECT * FROM transfer_receipts'):
        validate_uuid(row['package_id']); validate_uuid(row['source_installation_id']); _time(row['imported_at'])
        if not isinstance(row['content_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['content_sha256']): invalid()
        _integer(row['imported_count'])
    if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': invalid()


def _prepare(rows, platform, sequence):
    if platform not in APPS or not isinstance(rows,dict) or set(rows)!=set(TABLES): invalid()
    db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        for sql in V2.values(): db.execute(sql)
        indexes(db)
        result={}; used=0
        for table in TABLES:
            if not isinstance(rows[table],(list,tuple)) or len(rows[table])>CAPS[table]: invalid()
            info=tuple(db.execute('PRAGMA table_info('+table+')'))
            columns=tuple(column[1] for column in info)
            for source in rows[table]:
                row=dict(source)
                if set(row)!=set(columns): invalid()
                for column in info:
                    value=row[column[1]]
                    if value is None:
                        if column[1] not in ('helper_name','remarks','archived_at','before_json'): invalid()
                    elif column[2]=='INTEGER':
                        _integer(value)
                    elif not isinstance(value,str): invalid()
                encoded=canonical({'kind':table,'row':row})+b'\n'; used+=len(encoded)
                if len(encoded)>MAX_LINE or used>MAX_BYTES: invalid()
                db.execute('INSERT INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row[k] for k in columns))
            result[table]=[dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY '+ORDERS[table])]
        _validate(db,platform,sequence)
        return result
    except (sqlite3.Error,ValueError,TypeError,KeyError,IndexError,OverflowError,OfflineError):
        invalid()
    finally: db.close()


def state_digest(rows, platform, sequence):
    descriptor=dict(app_id=APPS[platform],platform=platform,schema_version=2,sequence=sequence)
    digest=hashlib.sha256(b'BHLI-STATE-v1\n'+canonical(descriptor)+b'\n')
    for table in TABLES:
        for row in rows[table]: digest.update(canonical({'kind':table,'row':dict(row)})+b'\n')
    return digest.hexdigest()


@dataclass(frozen=True)
class StateSnapshot:
    rows: object
    sequence: int | None
    platform: str
    digest: str
    metadata: object


def _snapshot(rows,sequence,platform,metadata=None):
    frozen=MappingProxyType({table:tuple(MappingProxyType(dict(row)) for row in rows[table]) for table in TABLES})
    meta=dict(metadata or {})
    if 'counts' in meta: meta['counts']=MappingProxyType(dict(meta['counts']))
    return StateSnapshot(frozen,sequence,platform,state_digest(rows,platform,sequence),MappingProxyType(meta))


def capture_state(repository, *, cancel=lambda:False):
    repository._check()
    with repository._transaction():
        return capture_transaction_state(repository._connection, cancel=cancel)


def capture_transaction_state(db, *, cancel=lambda:False):
    """Validate state inside an already owned transaction; never nest BEGIN."""
    if not db.in_transaction: invalid()
    if (db.execute('PRAGMA user_version').fetchone()[0]!=2 or not owned(db,2)
            or db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1").fetchone()): invalid()
    rows={}; used=0
    for table in TABLES:
        rows[table]=[]
        for source in db.execute('SELECT * FROM '+table+' ORDER BY '+ORDERS[table]):
            if cancel(): raise OfflineError('cancelled','Backup cancelled before completion.')
            row=dict(source); line=canonical({'kind':table,'row':row})+b'\n'; used+=len(line)
            if len(line)>MAX_LINE or used>MAX_BYTES or len(rows[table])>=CAPS[table]: invalid()
            rows[table].append(row)
    sequence=db.execute("SELECT seq FROM sqlite_sequence WHERE name='audit_records'").fetchone()
    watermark=None if sequence is None else sequence[0]
    validated=_prepare(rows,'windows',watermark)
    return _snapshot(validated,watermark,'windows')


def encode_state(rows, *, platform, sequence, backup_id, created_at, source_version):
    rows=_prepare(dict(rows),platform,sequence)
    validate_uuid(backup_id)
    if (not isinstance(created_at,str) or not re.fullmatch(r'[1-9][0-9]{3}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z',created_at)
            or not isinstance(source_version,str) or not 1<=len(source_version)<=64
            or any(ord(c)<32 or 127<=ord(c)<=159 for c in source_version)): invalid()
    _time(created_at)
    meta=dict(kind='metadata',payload_version=1,schema_version=2,platform=platform,app_id=APPS[platform],backup_id=backup_id,
              created_at=created_at,source_version=source_version,sqlite_sequence_audit_records=sequence,
              counts={table:len(rows[table]) for table in TABLES})
    output=bytearray(canonical(meta)+b'\n')
    for table in TABLES:
        for row in rows[table]:
            line=canonical({'kind':table,'row':row})+b'\n'
            if len(line)>MAX_LINE or len(output)+len(line)>MAX_BYTES: invalid()
            output.extend(line)
    end=canonical(dict(kind='end',rows=sum(map(len,rows.values())),content_bytes=len(output),state_sha256=state_digest(rows,platform,sequence)))+b'\n'
    if len(output)+len(end)>MAX_BYTES: invalid()
    return bytes(output)+end


def decode_state(raw, *, platform):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES or not raw.endswith(b'\n') or platform not in APPS: invalid()
    if raw.count(b'\n')>sum(CAPS.values())+2: invalid()
    lines=raw.splitlines(keepends=True)
    if len(lines)<2: invalid()
    meta=_json(lines[0],exact=True)
    keys={'kind','payload_version','schema_version','platform','app_id','backup_id','created_at','source_version','sqlite_sequence_audit_records','counts'}
    if (not isinstance(meta,dict) or set(meta)!=keys or meta['kind']!='metadata' or meta['payload_version']!=1
            or meta['schema_version']!=2 or meta['platform']!=platform or meta['app_id']!=APPS[platform]): invalid()
    rows={table:[] for table in TABLES}; position=0
    for line in lines[1:-1]:
        entry=_json(line,exact=True)
        if (not isinstance(entry,dict) or set(entry)!={'kind','row'}
                or not isinstance(entry['kind'],str) or entry['kind'] not in rows): invalid()
        index=TABLES.index(entry['kind'])
        if index<position or len(rows[entry['kind']])>=CAPS[entry['kind']]: invalid()
        position=index; rows[entry['kind']].append(entry['row'])
    # Re-encoding enforces canonical ordering, exact counts, metadata, ending and digest.
    expected=encode_state(rows,platform=platform,sequence=meta['sqlite_sequence_audit_records'],backup_id=meta['backup_id'],created_at=meta['created_at'],source_version=meta['source_version'])
    if expected!=raw: invalid()
    return _snapshot(rows,meta['sqlite_sequence_audit_records'],platform,meta)
