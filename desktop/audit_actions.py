"""Explicit ADMIN deletion with fresh identity and ambiguous-outcome reconciliation."""
from desktop.audit_operations import ambiguous
from desktop.components.audit_dialogs import confirm


def confirm_delete(app,record):
    if not app.session.login or app.session.login.user.role!='ADMIN':
        app.shell.notice.show('Only administrators may delete audits.')
        return
    if app.mutation_pending or app.dialog:
        return
    client,token,audit_id=app.client,app.session.login.token,record.id

    def resolved(current,error):
        if error:
            app.audit_unavailable(audit_id,error)
            app.shell.notice.show(str(error)+' Deletion was not confirmed. Reload and review before trying again.')
        elif current.deleted_at:
            app.navigate('Driver Audits',force=True)
            app.shell.notice.show('This audit is confirmed deleted. Its history remains available to administrators.',False)
        else:
            app.shell.notice.show('The audit is still active. Review its current identity and confirm again to delete.')
            show_confirmation(current)

    def deleted(result,error):
        if error:
            if ambiguous(error):
                app.shell.notice.show('Deletion outcome is unknown. Checking the current server state; no DELETE will be replayed.')
                app.request(lambda:client.get_audit(token,audit_id,include_deleted=True),resolved)
            elif error.status in (409,412):
                app.shell.notice.show('The record changed. Review the updated identity and confirm again.')
                app.request(lambda:client.get_audit(token,audit_id),resolved)
            else:
                app.audit_unavailable(audit_id,error)
                app.shell.notice.show(str(error)+' Deletion was not confirmed.')
            return
        app.navigate('Driver Audits',force=True)
        app.shell.notice.show('Audit soft-deleted. Original attribution and history are preserved.',False)

    def show_confirmation(current):
        if current.deleted_at or not current.etag:
            app.shell.notice.show('Reload the active record and its version before deletion.')
            return
        message=(f'Record #{current.id}\nDriver: {current.driver_name}\nPlate: {current.plate_number}\n'
                 f'Audit date: {current.audit_date}\n\nSoft deletion preserves history. This cannot be restored from this application.')
        def submit():
            app.mutate(lambda:client.delete_audit(token,audit_id,current.etag),deleted)
        confirm(app,'Delete this audit?',message,submit,'Soft-delete audit',destructive=True)

    def loaded(current,error):
        if error:
            app.audit_unavailable(audit_id,error)
            app.shell.notice.show(str(error))
        else:
            show_confirmation(current)
    app.request(lambda:client.get_audit(token,audit_id),loaded)
