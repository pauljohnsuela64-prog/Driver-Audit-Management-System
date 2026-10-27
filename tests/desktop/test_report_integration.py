"""Real REST/schema contracts on fixture-isolated SQLite or --mysql only."""
from uuid import uuid4
import pytest
from tests.test_auth import api,auth_engine,encoded_password,PASSWORD
from tests.desktop.test_account_integration import client_for
from tests.desktop.test_reports import cells
from desktop.models import AuditQuery
from desktop.reports import Destination,ExportControl,export_audits
from desktop.api import ApiError


def test_real_export_all_pages_text_and_archived_permissions(api,tmp_path):
    client=client_for(api);admin=client.sign_in('admin',PASSWORD)
    for index in range(105):
        record=client.create_audit(admin.token,dict(driver_name=f'Fictional José 李 {index:03}',
            station='Export Station',audit_date='2026-10-27',plate_number='000123',
            remarks='=HYPERLINK("https://example.com")' if index==0 else None),str(uuid4()))
    client.delete_audit(admin.token,record.id,record.etag)
    path=tmp_path/'all.xlsx'
    result=export_audits(client,admin.token,AuditQuery(station='Export Station',sort='audit_date',include_deleted=True),
        Destination.capture(path),ExportControl(),lambda p:None)
    values=cells(path)[1]
    assert result.count==105 and len(values)==106
    assert values[1][0]=='Fictional José 李 000' and values[1][4]=='000123'
    assert values[-1][-1]=='Archived' and all(line[6]==admin.user.full_name for line in values[1:])
    active=export_audits(client,admin.token,AuditQuery(station='Export Station'),Destination.capture(tmp_path/'active.xlsx'),ExportControl(),lambda p:None)
    assert active.count==104
    auditor=client.sign_in('auditor',PASSWORD)
    with pytest.raises(ApiError) as error:
        export_audits(client,auditor.token,AuditQuery(include_deleted=True),Destination.capture(tmp_path/'denied.xlsx'),ExportControl(),lambda p:None)
    assert error.value.status==403 and not (tmp_path/'denied.xlsx').exists()


def test_real_export_revoked_session_is_not_saved(api,tmp_path):
    client=client_for(api);admin=client.sign_in('admin',PASSWORD);client.logout(admin.token)
    with pytest.raises(ApiError) as error:
        export_audits(client,admin.token,AuditQuery(),Destination.capture(tmp_path/'x.xlsx'),ExportControl(),lambda p:None)
    assert error.value.status==401 and not list(tmp_path.glob('*.xlsx')) and not list(tmp_path.glob('.dams-export-*'))
