from types import SimpleNamespace
from threading import Event

def test_controller_tests_run_without_tk_dependencies():
    import os, subprocess, sys
    code = '''
import importlib.abc, sys
class BlockGui(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'tkinter', 'customtkinter', '_tkinter'}:
            raise ImportError('GUI dependency blocked: ' + fullname)
sys.meta_path.insert(0, BlockGui())
import pytest
raise SystemExit(pytest.main(['-q', 'tests/desktop/offline/test_transfer_ui.py', '-k', 'not native and not without_tk_dependencies']))
'''
    env = dict(os.environ, DAMS_DESKTOP_GUI_TESTS='0')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr

class App:
    closing=False
    def __init__(self): self.pending=[]
    def mutate(self,work,done): self.pending.append((work,done)); return True

class View:
    def __init__(self): self.messages=[]; self.results=[]
    def status(self,message,busy=False,error=False): self.messages.append((message,busy))
    def import_finished(self,result): self.results.append(result)


def test_import_apply_admitted_as_mutation_and_late_cancel_does_not_hide_commit():
    from desktop.offline.transfer_controller import TransferController
    app=App(); view=View(); controller=TransferController(app,view)
    preview=SimpleNamespace(new_ids=('one',),duplicate_ids=(),conflict_ids=())
    controller.apply(b'package',preview)
    assert len(app.pending)==1
    controller.cancel()
    result=SimpleNamespace(imported=1,duplicates=0,conflicts=0)
    app.pending[0][1](result,None)
    assert view.results==[result]
    assert not controller.pending


def test_cancel_sets_worker_token_without_touching_ui_from_work():
    from desktop.offline.transfer_controller import TransferController
    app=App(); view=View(); controller=TransferController(app,view)
    controller.apply(b'package',SimpleNamespace())
    token=controller.cancel_event
    controller.cancel()
    assert token.is_set()


def test_cancel_during_real_preview_does_not_publish_preview(tmp_path, monkeypatch):
    import pytest
    from desktop.offline.models import OfflineError, new_uuid
    from desktop.offline.repository import SqliteRepository
    from desktop.offline.transfer_controller import TransferController
    from desktop.offline.transfer_store import TransferStore
    source = SqliteRepository(tmp_path / 'cancel-source.db')
    source.save_profile('Fictional Source')
    source.create(new_uuid(), dict(driver_name='Fictional Driver', helper_name=None,
        audit_date='2026-01-01', station='Station', plate_number='001', remarks=None))
    path = tmp_path / 'cancel-preview.bhlitransfer'
    path.write_bytes(TransferStore(source).export())
    source.close()
    target = SqliteRepository(tmp_path / 'cancel-target.db')
    app = App(); view = View(); view.preview_ready = lambda *args: view.results.append(args)
    controller = TransferController(app, view)
    original = TransferStore.preview
    def preview_then_cancel(store, raw):
        result = original(store, raw)
        controller.cancel_event.set()
        return result
    monkeypatch.setattr(TransferStore, 'preview', preview_then_cancel)
    controller.preview(path)
    try:
        work, done = app.pending[0]
        with pytest.raises(OfflineError) as error:
            work(target)
        assert error.value.code == 'cancelled'
        done(None, error.value)
        assert view.results == []
        assert not controller.pending
        assert target._connection.execute('SELECT COUNT(*) FROM audit_records').fetchone()[0] == 0
        assert target._connection.execute('SELECT COUNT(*) FROM transfer_receipts').fetchone()[0] == 0
    finally:
        target.close()


def test_real_worker_export_file_preview_import_and_duplicate_recheck(tmp_path):
    import time
    from desktop.offline.lifecycle import OfflineLifecycle
    from desktop.offline.worker import DatabaseWorker
    from desktop.offline.repository import SqliteRepository
    from desktop.offline.models import new_uuid, AuditFilter
    from desktop.offline.transfer_controller import TransferController
    values=dict(driver_name='Fictional Driver',helper_name=None,audit_date='2026-01-01',station='Station',plate_number='001',remarks=None)
    source=tmp_path/'source.db'; target=tmp_path/'target.db'; destination=tmp_path/'copy.bhlitransfer'
    repo=SqliteRepository(source); repo.save_profile('Original Auditor'); audit=repo.create(new_uuid(),values); repo.close()
    repo=SqliteRepository(target); local=repo.save_profile('Recipient'); repo.close()
    class WorkerApp(OfflineLifecycle):
        closing=False; mutation_pending=False
        def __init__(self,path): self.worker=DatabaseWorker(lambda:SqliteRepository(path))
    class Results(View):
        def export_ready(self,*args): self.exported=args
        def export_finished(self,cleanup): self.published=cleanup
        def preview_ready(self,*args): self.previewed=args
    def wait(app,controller):
        deadline=time.monotonic()+5
        while controller.pending and time.monotonic()<deadline:
            app.worker.drain(); time.sleep(.005)
        assert not controller.pending
    source_app=WorkerApp(source); target_app=WorkerApp(target)
    source_view=Results(); target_view=Results()
    export=TransferController(source_app,source_view); importer=TransferController(target_app,target_view)
    try:
        export.export(); wait(source_app,export)
        raw,records,events=source_view.exported
        assert (records,events)==(1,1)
        export.publish(raw,destination); wait(source_app,export)
        assert source_view.published and destination.read_bytes()==raw
        importer.preview(destination); wait(target_app,importer)
        raw,preview=target_view.previewed
        assert preview.new_ids==(audit.id,)
        importer.apply(raw,preview); wait(target_app,importer)
        assert target_view.results[0].imported==1
        importer.preview(destination); wait(target_app,importer)
        assert target_view.previewed[1].duplicate_ids==(audit.id,)
    finally:
        for app in (source_app,target_app): app.worker.close(); app.worker.join(); app.worker.drain()
    repo=SqliteRepository(target)
    assert repo.profile()==local
    assert repo.list(AuditFilter()).items[0].audited_by_name=='Original Auditor'
    repo.close()


def test_native_transfer_view_export_preview_confirmation_and_import(tmp_path,monkeypatch):
    import os, sys, time
    import pytest
    if os.getenv('DAMS_DESKTOP_GUI_TESTS')!='1' or sys.platform!='win32':
        pytest.skip('Native Windows transfer UI requires DAMS_DESKTOP_GUI_TESTS=1')
    from desktop.offline.app import OfflineApplication
    from desktop.offline.repository import SqliteRepository
    from desktop.offline.transfer_store import TransferStore
    from desktop.offline.models import new_uuid
    from desktop.offline import transfer_ui
    values=dict(driver_name='Fictional Driver',helper_name=None,audit_date='2026-01-01',station='Station',plate_number='001',remarks=None)
    source=tmp_path/'native-source.db'; target=tmp_path/'native-target.db'; incoming=tmp_path/'incoming.bhlitransfer'; outgoing=tmp_path/'outgoing.bhlitransfer'
    repo=SqliteRepository(source); repo.save_profile('Source'); audit=repo.create(new_uuid(),values); incoming.write_bytes(TransferStore(repo).export()); repo.close()
    repo=SqliteRepository(target); repo.save_profile('Recipient'); repo.close()
    import customtkinter as ctk
    from tests.desktop.native_capture import capture
    from pathlib import Path
    callback_errors=[]
    ctk.set_appearance_mode('Light')
    app=OfflineApplication(target)
    app.report_callback_exception=lambda *args:callback_errors.append(args)
    screenshots=Path('artifacts/phase6d/windows-transfer'); screenshots.mkdir(parents=True,exist_ok=True)
    def screenshot(name):
        settle=time.monotonic()+.25
        while time.monotonic()<settle:
            app.update(); time.sleep(.01)
        capture(app.winfo_id(),screenshots/name)
    def pump(predicate,timeout=8):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.update()
            if predicate(): return
            time.sleep(.01)
        assert predicate()
    try:
        pump(lambda: hasattr(app.screen, 'name'))
        app.screen.save()
        pump(lambda: app.shell is not None)
        app.navigate('Driver Audits')
        app.screen.transfer_button.invoke()
        assert 'Transfer audits' not in app.shell.nav_buttons
        view=app.screen
        app.geometry('800x650')
        screenshot('transfer-light-compact.png')
        app.set_theme('Dark'); app.update(); screenshot('transfer-dark-compact.png')
        view=app.screen
        monkeypatch.setattr(transfer_ui.filedialog,'askopenfilename',lambda **kwargs:str(incoming))
        monkeypatch.setattr(transfer_ui.filedialog,'asksaveasfilename',lambda **kwargs:str(outgoing))
        view.open_import()
        pump(lambda: view.preview_result is not None)
        assert view.preview_result.new_ids==(audit.id,)
        view._parent_canvas.yview_moveto(1)
        screenshot('import-preview-dark.png')
        view.confirm_import()
        pump(lambda:app.dialog is not None)
        app.update(); capture(app.dialog.winfo_id(),screenshots/'import-confirmation-dark.png')
        app.dialog.accept()
        pump(lambda:app.destination=='Driver Audits' and not app.mutation_pending)
        app.open_transfer(); view=app.screen
        view.export()
        pump(lambda:outgoing.exists() and not app.mutation_pending)
        assert outgoing.read_bytes().startswith(b'PK')
        assert app.profile.name=='Recipient'
        assert callback_errors==[]
    finally:
        app.close(force=True)
        pump(lambda:app.closed)


def test_detached_view_gets_no_callback_and_commit_is_reported_at_app_level():
    from desktop.offline.transfer_controller import TransferController
    app=App(); app.messages=[]; app._notice=lambda *args:app.messages.append(args)
    app.refresh=lambda:None
    view=View(); view.winfo_exists=lambda:False
    controller=TransferController(app,view)
    controller.apply(b'package',SimpleNamespace())
    result=SimpleNamespace(imported=2,duplicates=1,conflicts=0)
    app.pending[0][1](result,None)
    assert view.results==[]
    assert '2 new' in app.messages[-1][0]
    assert not controller.pending


def test_conflict_confirmation_requires_explicit_skip_consent():
    from desktop.offline.transfer_controller import confirm_import
    calls=[]; applied=[]
    preview=SimpleNamespace(new_ids=('new',),duplicate_ids=('duplicate',),conflict_ids=('different',))
    controller=SimpleNamespace(pending=False,apply=lambda *args:applied.append(args))
    view=SimpleNamespace(app=App(),raw=b'package',preview_result=preview,controller=controller)
    confirm_import(view, lambda *args:calls.append(args))
    assert applied==[]
    assert '1 conflicting audits' in calls[0][2]
    assert 'skip conflicts' in calls[0][4]
    calls[0][3]()
    assert applied==[(b'package',preview)]
