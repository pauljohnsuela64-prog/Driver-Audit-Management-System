"""Minimal administrator account management within My Account."""
from threading import Event
import customtkinter as ctk
from desktop.api import ApiError
from desktop.account_operations import AccountAction,account_error,list_admins,target_admin
from desktop.audit_operations import ambiguous
from desktop.components.common import button,label,Notice,destroy_view
from desktop.components.audit_dialogs import confirm
from desktop.screens.account_form import AccountForm
from desktop.theme import color


class Account(ctk.CTkScrollableFrame):
    def __init__(self,parent,app):
        super().__init__(parent,fg_color=color('surface'),corner_radius=12)
        self.app=app
        self.loaded=False;self.admins=();self.expanded=False;self.form=None
        self.cancelled=Event();self.columnconfigure(0,weight=1)
        user=app.session.login.user
        label(self,'My Account',28).grid(row=0,column=0,sticky='w',padx=24,pady=(24,8))
        label(self,f'{user.full_name}\n{user.username}',16,justify='left',wraplength=500).grid(row=1,column=0,sticky='w',padx=24,pady=(0,8))
        label(self,'Session expires '+app.session.login.expires_at.strftime('%Y-%m-%d %H:%M UTC'),12,True).grid(row=2,column=0,sticky='w',padx=24)
        self.change_button=button(self,'Change My Password',lambda:self.open_form('change'),width=210)
        self.change_button.grid(row=3,column=0,sticky='w',padx=24,pady=16)
        self.notice=Notice(self);self.notice.grid(row=4,column=0,sticky='ew',padx=24,pady=(0,8))
        self.forms=ctk.CTkFrame(self,fg_color='transparent')
        self.forms.grid(row=5,column=0,sticky='ew',padx=24,pady=(0,12));self.forms.columnconfigure(0,weight=1)
        self.manage_button=button(self,'Manage Admin Accounts',self.toggle_manage,width=240)
        self.manage_button.grid(row=6,column=0,sticky='w',padx=24,pady=(12,8))
        self.manage=ctk.CTkFrame(self,fg_color='transparent');self.manage.grid(row=7,column=0,sticky='ew',padx=24,pady=(0,24))
        self.manage.columnconfigure(0,weight=1)
        actions=ctk.CTkFrame(self.manage,fg_color='transparent');actions.grid(row=0,column=0,sticky='ew',pady=(0,12))
        self.add_button=button(actions,'Add Administrator',lambda:self.open_form('add'),True,width=200)
        self.add_button.pack(side='left',padx=(0,8))
        self.refresh_button=button(actions,'Refresh',self.refresh,width=100);self.refresh_button.pack(side='left')
        self.cards=ctk.CTkFrame(self.manage,fg_color='transparent');self.cards.grid(row=1,column=0,sticky='ew');self.cards.columnconfigure(0,weight=1)
        self.manage.grid_remove()
        self.buttons=[self.change_button,self.manage_button,self.add_button,self.refresh_button]
        self.render_action()
        if not self.busy():self.refresh()

    def busy(self):
        return bool(self.app.mutation_pending or self.app.account_action and self.app.account_action.pending)

    def toggle_manage(self):
        if self.busy():return
        self.expanded=not self.expanded
        if self.expanded:self.manage.grid();self.refresh()
        else:self.manage.grid_remove()

    def on_leave(self):
        self.cancelled.set()
        if self.form:self.form.clear_secrets()

    def reveal(self,widget):
        def scroll():
            canvas=self._parent_canvas;region=canvas.bbox('all')
            if not region:return
            y=widget.winfo_rooty()-self.winfo_rooty();top=canvas.canvasy(0);height=canvas.winfo_height()
            if y<top or y+widget.winfo_height()>top+height:
                canvas.yview_moveto(max(0,y-24)/max(1,region[3]))
        self.after_idle(scroll)

    def clear_form(self):
        if self.form:self.form.clear_secrets();destroy_view(self.form);self.form=None

    def open_form(self,kind,target=None):
        if self.busy():return
        self.clear_form();self.form=AccountForm(self.forms,self,kind,target)
        self.form.grid(row=0,column=0,sticky='ew')
        self.after_idle(lambda:self.form.fields[next(iter(self.form.fields))].focus_set() if self.form else None)

    def open_target(self,kind,user):
        if self.busy():return
        self.clear_form();actor=self.app.session.login.user
        if actor.id==user.id:
            self.notice.show('Use Change My Password for your own account; you cannot disable yourself.');return
        client,token=self.app.client,self.app.session.login.token
        def loaded(target,error):
            if error:self.clear_cards();self.notice.show(account_error(error));return
            if kind=='reset':self.open_form('reset',target)
            elif target.is_active:
                confirm(self.app,'Disable administrator?',f'{target.full_name}\n{target.username} (#{target.id})\n\nTheir sessions will be revoked. Existing audits and attribution are preserved.',
                        lambda:self.start_action('disable',target,{}),'Disable administrator',destructive=True)
            else:self.notice.show('This administrator is already disabled. Refresh the list.')
        self.app.request(lambda:target_admin(client,token,actor.id,user.id),loaded)

    def clear_cards(self):
        self.admins=()
        for child in self.cards.winfo_children():destroy_view(child)
        self.buttons=self.buttons[:4]

    def refresh(self):
        if self.busy():return
        self.loaded=False;self.clear_cards()
        self.cancelled.set();self.cancelled=Event();cancelled=self.cancelled
        client,token,actor_id=self.app.client,self.app.session.login.token,self.app.session.login.user.id
        expanded=self.expanded
        self.notice.show('Loading administrator accounts…' if expanded else 'Checking account access…',False)
        def work():
            identity=client.me(token)
            if identity.role!='ADMIN' or identity.id!=actor_id:raise ApiError(401)
            return list_admins(client,token,cancelled) if expanded else ()
        def loaded(users,error):
            if error:self.notice.show(account_error(error)+' The account list is unavailable; Refresh to retry.');return
            self.loaded=True;self.admins=users
            for i,user in enumerate(users):
                card=ctk.CTkFrame(self.cards,fg_color=color('raised'),corner_radius=8)
                card.grid(row=i,column=0,sticky='ew',pady=(0,10));card.columnconfigure(0,weight=1)
                label(card,user.full_name,16,anchor='w',wraplength=500).grid(row=0,column=0,sticky='ew',padx=16,pady=(12,0))
                label(card,f'{user.username} · '+('Active' if user.is_active else 'Disabled')+(' · You' if user.id==actor_id else ''),12,True,
                      anchor='w',wraplength=500).grid(row=1,column=0,sticky='ew',padx=16,pady=(0,8))
                if user.id!=actor_id:
                    controls=ctk.CTkFrame(card,fg_color='transparent');controls.grid(row=2,column=0,sticky='ew',padx=16,pady=(0,12))
                    reset=button(controls,'Reset password',lambda u=user:self.open_target('reset',u),width=170)
                    reset.pack(side='left',padx=(0,8));self.buttons.append(reset)
                    if user.is_active:
                        disable=button(controls,'Disable',lambda u=user:self.open_target('disable',u),width=100)
                        disable.pack(side='left');self.buttons.append(disable)
            self.notice.show('No administrator accounts found.' if expanded and not users else '',False);self.render_action()
        self.app.request(work,loaded)

    def render_action(self):
        action=self.app.account_action;busy=self.busy()
        for widget in self.buttons:widget.configure(state='disabled' if busy else 'normal')
        if self.form:self.form.submit_button.configure(state='disabled' if busy else 'normal')
        if action:self.notice.show('Submitting account action…' if action.pending else action.message,action.failed)

    def operation_finished(self,action):
        self.clear_form();self.render_action();self.refresh()

    def start_action(self,kind,target,values):
        if self.busy():return
        app,client,login=self.app,self.app.client,self.app.session.login
        target_id=target.id if target else None
        action=AccountAction(kind,target_id);app.account_action=action
        # Only primitive request values cross to workers. Never capture widgets.
        if kind=='add':
            username,full_name,password=values['username'],values['full_name'],values['password']
            work=lambda:client.create_admin(login.token,username,full_name,password)
        elif kind=='change':
            current,new=values['current_password'],values['new_password']
            work=lambda:client.change_password(login.token,current,new)
        else:
            admin_password,new=values.get('admin_password'),values.get('new_password')
            def work():
                fresh=target_admin(client,login.token,login.user.id,target_id)
                if kind=='disable':
                    if not fresh.is_active:raise ApiError(409,code='access_conflict')
                    return client.disable_admin(login.token,target_id)
                return client.reset_admin_password(login.token,target_id,admin_password,new)
        def display():
            screen=app.screen
            if app.destination=='My Account' and hasattr(screen,'operation_finished'):screen.operation_finished(action)
        def completed(result,error):
            action.pending=False
            if error:
                action.failed=True;action.uncertain=ambiguous(error);action.message=account_error(error)
                if action.uncertain:
                    action.message+=' Outcome unknown; do not automatically repeat this action.'
                    if kind=='change':
                        app.logout('Password change outcome is unknown. Please sign in; the replacement password may already be in effect.',force=True);return
                    if kind=='add':action.message+=' Refresh and inspect the intended username before adding another administrator.'
                    if kind=='disable':
                        action.pending=True
                        def reconciled(user,read_error):
                            action.pending=False
                            if read_error:action.message+=' Account status could not be confirmed; Refresh before deciding.'
                            elif not user.is_active:
                                action.uncertain=False;action.failed=False;action.message='The account is confirmed disabled.'
                            else:action.message='The account is still active. Refresh and confirm again before another disable request.'
                            display()
                        # Outcome reconciliation must survive read supersession/theme rebuilds.
                        app.mutate(lambda:client.get_user(login.token,target_id),reconciled);return
            elif kind=='change':
                app.logout('Password changed. All sessions were revoked; please sign in again.',force=True,revoke=False);return
            else:
                action.message={'add':'Administrator added.','reset':'Password reset; target sessions revoked. Account status is unchanged.',
                                'disable':'Administrator disabled; target sessions revoked. Existing audits are preserved.'}[kind]
            display()
        app.mutate(work,completed);self.render_action()
