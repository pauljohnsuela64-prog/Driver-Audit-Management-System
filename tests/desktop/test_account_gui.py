"""Native account and density checks, opt-in on Windows only."""
from tkinter import ttk

from tests.desktop.test_gui import app, sign_in, pump, pytestmark


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
