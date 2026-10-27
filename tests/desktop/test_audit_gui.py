"""Native acceptance of audit forms and session-scoped operation delivery."""
from threading import Event

import pytest

from desktop.api import ApiError
from tests.desktop.test_gui import app, sign_in, pump, pytestmark
from tests.desktop.test_api import AUDIT
from desktop.models import Audit


def fill(screen):
    for key,value in dict(driver_name='Desktop Example',audit_date='2026-10-27',
                          station='Example Station',plate_number='DEMO-NEW',remarks='Optional notes').items():
        widget=screen.inputs[key]
        if key=='remarks':
            widget.delete('1.0','end'); widget.insert('1.0',value)
        else:
            widget.delete(0,'end'); widget.insert(0,value)


def test_create_validation_theme_and_ambiguous_retry(app):
    sign_in(app)
    app.open_create()
    screen=app.screen
    screen.save()
    assert 'driver_name' in app.draft.errors
    fill(screen)
    calls=[]
    def create(token,payload,key):
        calls.append((payload,key))
        if len(calls)==1:
            raise ApiError()
        return Audit.parse(AUDIT,'"2"')
    app.client.create_audit=create
    screen.save()
    pump(app,lambda: app.draft is not None and app.draft.uncertain)
    app.set_theme('Dark')
    assert app.screen.inputs['driver_name'].get()=='Desktop Example'
    app.screen.save()
    pump(app,lambda: app.destination=='Audit Details')
    assert len(calls)==2 and calls[0]==calls[1]


def test_mutation_not_dropped_by_read_supersession_or_delivered_after_logout(app):
    sign_in(app)
    gate=Event(); finished=[]
    app.mutate(lambda:gate.wait(3),lambda result,error:finished.append(result))
    app.tasks.invalidate()
    app.logout(force=True)
    gate.set()
    pump(app,lambda:not app.mutation_pending)
    assert finished==[] and app.session.login is None


def test_edit_partial_changes_and_conflict_requires_review(app):
    sign_in(app)
    app.open_edit(Audit.parse(AUDIT,'"2"'))
    pump(app,lambda:hasattr(app.screen,'inputs'))
    screen=app.screen
    field=screen.inputs['driver_name'];field.delete(0,'end');field.insert(0,'Edited')
    calls=[]
    def update(token,id,payload,etag):
        calls.append((payload,etag))
        if len(calls)==1:
            raise ApiError(412)
        return Audit.parse(dict(AUDIT,driver_name='Edited',version=4),'"4"')
    app.client.update_audit=update
    app.client.get_audit=lambda *args,**kw:Audit.parse(dict(AUDIT,station='Changed elsewhere',version=3),'"3"')
    screen.save()
    pump(app,lambda:app.draft is not None and app.draft.latest is not None)
    assert len(calls)==1 and app.draft.values['driver_name']=='Edited'
    app.screen.reapply()
    app.screen.save()
    pump(app,lambda:app.destination=='Audit Details')
    assert calls[1][1]=='"3"'
    assert calls[1][0]['driver_name']=='Edited'


def test_form_navigation_requires_discard_and_auditor_cannot_edit_other_owner(app):
    sign_in(app,'auditor')
    app.open_edit(Audit.parse(dict(AUDIT,audited_by_user_id=999),'"2"'))
    pump(app)
    assert app.destination=='Dashboard'
    app.open_create();fill(app.screen)
    app.navigate('Driver Audits')
    assert app.dialog is not None and app.destination=='Create Audit'
    app.dialog.cancel()
    assert app.destination=='Create Audit'
    app.navigate('Driver Audits');app.dialog.accept()
    assert app.destination=='Driver Audits' and app.draft is None


def test_delete_stale_requires_new_identity_confirmation(app):
    sign_in(app)
    original=Audit.parse(AUDIT,'"2"')
    latest=Audit.parse(dict(AUDIT,driver_name='Changed identity',version=3),'"3"')
    app.client.get_audit=lambda *args,**kw:original
    calls=[]
    def delete(token,id,etag):
        calls.append(etag)
        if len(calls)==1:
            app.client.get_audit=lambda *args,**kw:latest
            raise ApiError(412)
    app.client.delete_audit=delete
    app.confirm_delete(original)
    pump(app,lambda:app.dialog is not None)
    app.dialog.accept()
    pump(app,lambda:app.dialog is not None and not app.mutation_pending)
    assert calls==['"2"'] and 'Changed identity' in app.dialog.message.cget('text')
    app.dialog.accept()
    pump(app,lambda:app.destination=='Driver Audits')
    assert calls==['"2"','"3"']


def test_delete_ambiguous_success_reconciles_without_replay(app):
    sign_in(app)
    original=Audit.parse(AUDIT,'"2"')
    deleted=Audit.parse(dict(AUDIT,deleted_at='2026-10-27T01:00:00Z'),allow_deleted=True)
    app.client.get_audit=lambda *args,**kw:deleted if kw.get('include_deleted') else original
    calls=[]
    def delete(*args):
        calls.append(args)
        raise ApiError()
    app.client.delete_audit=delete
    app.confirm_delete(original)
    pump(app,lambda:app.dialog is not None)
    app.dialog.accept()
    pump(app,lambda:app.destination=='Driver Audits')
    assert len(calls)==1 and 'deleted' in app.shell.notice.cget('text').lower()


def test_history_deleted_readonly_and_auditor_no_delete(app):
    from desktop.models import EventPage
    from tests.desktop.test_audit_api import event
    sign_in(app)
    app.client.audit_history=lambda *args,**kw:EventPage.parse(dict(items=[event()],total=1,page=1,page_size=25),1)
    app.navigate('Audit History',1)
    pump(app,lambda:app.screen.loaded)
    assert app.screen.events.items[0].actor_user_id==2
    app.logout(force=True);sign_in(app,'auditor')
    app.confirm_delete(Audit.parse(AUDIT,'"2"'))
    assert app.dialog is None and app.destination=='Dashboard'


def test_compact_form_uses_available_width_and_wide_form_has_two_columns(app):
    sign_in(app)
    app.geometry('800x600');app.open_create()
    for _ in range(8):
        pump(app)
    assert app.screen._columns==1
    assert app.screen.inputs['driver_name'].winfo_width()>app.screen.body.winfo_width()*.8
    app.geometry('1400x800')
    import time
    for _ in range(8):
        pump(app);time.sleep(.02)
    assert app.screen._columns==2
    assert app.screen.groups['driver_name'].grid_info()['row']==app.screen.groups['helper_name'].grid_info()['row']
