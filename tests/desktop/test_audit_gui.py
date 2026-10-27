"""Native acceptance of audit forms and session-scoped operation delivery."""
from threading import Event

import pytest

from desktop.api import ApiError
from tests.desktop.test_gui import native_app, app, sign_in, pump, pytestmark
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
