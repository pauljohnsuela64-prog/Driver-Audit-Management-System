"""Native account and density checks, opt-in on Windows only."""
from tkinter import ttk

from tests.desktop.test_gui import app, sign_in, pump, pytestmark
from desktop.api import ApiError
from desktop.models import Account,AccountPage


def account_setup(app):
    sign_in(app)
    users=(Account(1,'admin','Example Employee','ADMIN',True),Account(2,'other','Other Administrator','ADMIN',True))
    app.client.list_users=lambda token,page=1:AccountPage(users,2,page,100)
    app.client.get_user=lambda token,id:next(user for user in users if user.id==id)
    app.navigate('My Account');pump(app,lambda:app.screen.loaded)
    app.screen.toggle_manage();pump(app,lambda:app.screen.loaded and len(app.screen.admins)==2)
    return users


def populate(form,values):
    for key,value in values.items():
        form.fields[key].delete(0,'end');form.fields[key].insert(0,value)


def test_shared_table_density_and_dashboard_quick_create(app):
    sign_in(app)
    pump(app,lambda:app.screen.loaded)
    from desktop.components.table import AuditTable
    def find(widget):
        if isinstance(widget,AuditTable):return widget
        for child in widget.winfo_children():
            result=find(child)
            if result:return result
    recent=find(app.screen)
    style=ttk.Style(recent)
    assert int(style.lookup('BHLI.Treeview','rowheight'))==round(38*recent._get_widget_scaling())
    assert int(recent.tree.column('audit_date','stretch'))==0
    assert recent.tree.item(recent.tree.get_children()[1],'tags')==('alternate',)
    assert app.screen.create_button.winfo_ismapped()
    app.screen.create_button.invoke()
    assert app.destination=='Create Audit'


def test_dashboard_create_available_offline(app):
    sign_in(app)
    app.client.transport.mode='offline'
    app.screen.refresh();pump(app)
    assert app.screen.create_button.winfo_ismapped()


def test_account_add_validation_secret_clearing_and_background_http(app):
    from threading import get_ident
    users=account_setup(app);calls=[];owner=get_ident()
    def create(*args):calls.append((get_ident(),args));return Account(3,'third','Third Admin','ADMIN',True)
    app.client.create_admin=create
    app.screen.open_form('add');form=app.screen.form
    form.submit();assert not calls and 'required' in form.status.cget('text').lower()
    populate(form,dict(username='third',full_name='Third Admin',password='fictional new passphrase',confirm_password='fictional new passphrase'))
    form.submit()
    assert form.fields['password'].get()=='' and form.fields['confirm_password'].get()==''
    pump(app,lambda:app.account_action is not None and not app.account_action.pending)
    assert calls[0][0]!=owner and calls[0][1][1:3]==('third','Third Admin')


def test_reset_requires_fresh_target_and_reauthentication(app):
    users=account_setup(app);calls=[]
    app.client.reset_admin_password=lambda *args:calls.append(args)
    app.screen.open_target('reset',users[1]);pump(app,lambda:app.screen.form is not None)
    form=app.screen.form
    populate(form,dict(admin_password='current fictional password',new_password='replacement fictional password',confirm_password='replacement fictional password'))
    form.submit();pump(app,lambda:app.account_action is not None and not app.account_action.pending)
    assert calls[0][1]==2 and calls[0][2]=='current fictional password'
    app.screen.open_target('reset',users[0]);pump(app)
    assert len(calls)==1 and app.screen.form is None


def test_own_password_change_clears_session_and_requires_login(app):
    account_setup(app);calls=[]
    app.client.change_password=lambda *args:calls.append(args)
    app.screen.open_form('change');form=app.screen.form
    populate(form,dict(current_password='current fictional password',new_password='replacement fictional password',confirm_password='replacement fictional password'))
    form.submit();pump(app,lambda:app.session.login is None)
    assert len(calls)==1 and 'sign in' in app.screen.status.cget('text').lower()


def test_disable_conflict_and_ambiguous_outcome_never_auto_replay(app):
    users=account_setup(app);calls=[]
    def disable(*args):calls.append(args);raise ApiError(409,code='last_admin')
    app.client.disable_admin=disable
    app.screen.open_target('disable',users[1]);pump(app,lambda:app.dialog is not None)
    app.dialog.accept();pump(app,lambda:app.account_action is not None and not app.account_action.pending)
    assert len(calls)==1 and 'last active' in app.account_action.message
    pump(app,lambda:app.screen.loaded and not app.screen.loading)
    def uncertain(*args):calls.append(args);raise ApiError()
    app.client.disable_admin=uncertain
    app.screen.open_target('disable',users[1]);pump(app,lambda:app.dialog is not None)
    app.dialog.accept();pump(app,lambda:not app.account_action.pending)
    assert len(calls)==2 and 'active' in app.account_action.message.lower()


def test_theme_clears_password_fields_and_preserves_pending_action(app):
    from threading import Event
    account_setup(app)
    app.screen.open_form('change')
    populate(app.screen.form,dict(current_password='not retained on theme'))
    app.set_theme('Dark');pump(app)
    assert app.screen.form is None
    gate=Event();started=Event()
    def create(*args):started.set();gate.wait(3);return Account(3,'third','Third','ADMIN',True)
    app.client.create_admin=create
    app.screen.open_form('add')
    populate(app.screen.form,dict(username='third',full_name='Third',password='fictional new passphrase',confirm_password='fictional new passphrase'))
    app.screen.form.submit();pump(app,started.is_set)
    app.set_theme('Light');pump(app)
    assert app.account_action.pending and app.screen.form is None
    gate.set();pump(app,lambda:not app.account_action.pending)


def test_theme_during_disable_reconciliation_does_not_strand_action(app):
    from threading import Event
    users=account_setup(app);gate=Event();started=Event();reads=[]
    def get_user(token,id):
        reads.append(id)
        if len(reads)==3:started.set();gate.wait(3)
        return users[1]
    app.client.get_user=get_user
    def disable(*args):raise ApiError()
    app.client.disable_admin=disable
    app.screen.open_target('disable',users[1]);pump(app,lambda:app.dialog is not None)
    app.dialog.accept();pump(app,started.is_set)
    app.set_theme('Dark');pump(app)
    gate.set();pump(app,lambda:not app.account_action.pending)


def test_refresh_does_not_start_overlapping_scans(app):
    from threading import Event
    users=account_setup(app);started=Event();gate=Event();calls=[]
    def listing(token,page=1):
        calls.append(page);started.set();gate.wait(3)
        return AccountPage(users,2,page,100)
    app.client.list_users=listing
    try:
        app.screen.refresh();pump(app,started.is_set)
        app.screen.refresh();app.screen.refresh()
        import time
        for _ in range(5):pump(app);time.sleep(.02)
        assert len(calls)==1
    finally:gate.set()
    pump(app,lambda:app.screen.loaded)


def test_permission_loss_clears_password_form_and_blocks_actions_until_refresh(app):
    users=account_setup(app)
    app.screen.open_form('change')
    form=app.screen.form;form.fields['current_password'].insert(0,'not retained after denial')
    def denied(*args):raise ApiError(403)
    app.client.list_users=denied
    app.screen.refresh();pump(app,lambda:'unavailable' in app.screen.notice.cget('text'))
    assert app.screen.form is None and not app.screen.admins
    assert app.screen.add_button.cget('state')=='disabled'
    app.client.list_users=lambda token,page=1:AccountPage(users,2,page,100)
    app.screen.refresh();pump(app,lambda:app.screen.loaded)
    assert app.screen.add_button.cget('state')=='normal'


def test_old_mutation_completion_releases_new_account_view_without_old_result(app):
    from threading import Event
    account_setup(app);gate=Event();started=Event()
    def create(*args):started.set();gate.wait(3);return Account(3,'old_private','Old Account','ADMIN',True)
    app.client.create_admin=create
    app.screen.open_form('add')
    populate(app.screen.form,dict(username='old_private',full_name='Old Account',password='fictional new passphrase',confirm_password='fictional new passphrase'))
    app.screen.form.submit();pump(app,started.is_set)
    app.logout(force=True);sign_in(app,'admin2');app.navigate('My Account',force=True)
    gate.set();pump(app,lambda:not app.mutation_pending)
    pump(app,lambda:app.screen.change_button.cget('state')=='normal')
    assert app.account_action is None and 'old_private' not in app.screen.notice.cget('text')
