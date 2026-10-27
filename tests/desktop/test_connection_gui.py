from pathlib import Path
from threading import get_ident
from tests.desktop.test_gui import app,pump,sign_in,pytestmark
from desktop.settings import Endpoint
from desktop.config import Config


def test_first_connection_required_then_saved_without_token(app,tmp_path):
    app.settings_file=tmp_path/'settings.json'
    app.endpoint=Endpoint(None,'Not configured')
    app.show_login()
    assert app.screen.submit_button.cget('state')=='disabled'
    app.open_connection();pump(app)
    dialog=app.dialog;dialog.origin_field.insert(0,'https://api.example.com')
    dialog.save();pump(app)
    assert app.endpoint.config.base_url=='https://api.example.com'
    assert app.settings_file.exists() and app.screen.submit_button.cget('state')=='normal'
    assert app.session.login is None and app.dialog is None


def test_health_on_worker_and_invalid_url_feedback(app,tmp_path,monkeypatch):
    from desktop.api import ApiClient
    app.settings_file=tmp_path/'settings.json';calls=[];owner=get_ident()
    monkeypatch.setattr(ApiClient,'health',lambda client:calls.append(get_ident()) or True)
    app.open_connection();pump(app);dialog=app.dialog
    dialog.origin_field.delete(0,'end');dialog.origin_field.insert(0,'http://192.168.0.10')
    dialog.test();assert not calls
    dialog.origin_field.delete(0,'end');dialog.origin_field.insert(0,'https://api.example.com')
    dialog.test();pump(app,lambda:bool(calls) and not dialog.pending)
    assert calls[0]!=owner and 'not verified' in dialog.status.cget('text')
    dialog.cancel()


def test_operator_override_and_authenticated_settings_are_protected(app,tmp_path):
    app.endpoint=Endpoint(Config('https://managed.example.com'),'Environment',locked=True)
    app.settings_file=tmp_path/'settings.json';app.show_login();app.open_connection();pump(app)
    assert app.dialog.origin_field.cget('state')=='disabled' and app.dialog.confirm_button.cget('state')=='disabled'
    app.dialog.cancel()
    app.endpoint=Endpoint(Config(),'Developer default');app.show_login();sign_in(app)
    app.open_connection();assert app.dialog is None and app.session.login is not None
