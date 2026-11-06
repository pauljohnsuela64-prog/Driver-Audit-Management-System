"""GUI-independent transfer admission, cancellation, and explicit consent."""
from threading import Event
from desktop.offline.models import OfflineError
from desktop.offline.transfer_files import publish_transfer, read_transfer

class TransferController:
    def __init__(self, app, view):
        self.app, self.view = app, view
        self.pending = False
        self.cancel_event = Event()

    def _alive(self):
        try:
            return not hasattr(self.view, 'winfo_exists') or bool(self.view.winfo_exists())
        except Exception:
            # A destroyed GUI adapter can raise without the controller importing Tk.
            return False

    def _detached(self, result, operation):
        if operation == 'import':
            self.app.refresh()
            self.app._notice(f'Import confirmed: {result.imported} new, {result.duplicates} duplicates skipped, {result.conflicts} conflicts skipped.', False)
        elif operation == 'publish':
            self.app._notice('Transfer file saved and flushed.' + ('' if result else ' An owned temporary sibling could not be removed.'), False)
        else:
            self.app._notice('Transfer operation completed. Return to Transfer audits to continue. A prepared export is only saved after a destination is chosen.', False)

    def _submit(self, work_factory, completed, message, operation='transfer'):
        if self.pending or self.app.closing:
            return False
        self.pending = True
        self.cancel_event = Event()
        token = self.cancel_event
        self.view.status(message, True)
        def done(result, error):
            self.pending = False
            if self.app.closing:
                return
            if not self._alive():
                if error:
                    self.app._notice(str(error))
                else:
                    self._detached(result, operation)
            elif error:
                self.view.status(str(error), error=True)
            else:
                completed(result)
        # Mutation admission keeps accepted export/file work alive during close,
        # and prevents navigation from discarding an admitted import result.
        return self.app.mutate(work_factory(token), done)

    def export(self, date_from=None, date_to=None):
        def factory(token):
            def work(repo):
                from desktop.offline.transfer_store import TransferStore
                from desktop.offline.transfer import decode_transfer
                raw = TransferStore(repo).export(date_from=date_from, date_to=date_to, cancel=token.is_set)
                package = decode_transfer(raw)
                return raw, len(package.audits), len(package.events)
            return work
        return self._submit(factory, lambda result: self.view.export_ready(*result), 'Preparing selected audits and history...')

    def publish(self, raw, path):
        def factory(token):
            return lambda repo: publish_transfer(path, raw, cancel=token.is_set)
        return self._submit(factory, self.view.export_finished, 'Writing and checking the transfer file...', operation='publish')

    def preview(self, path):
        def factory(token):
            def work(repo):
                from desktop.offline.transfer_store import TransferStore
                raw = read_transfer(path, cancel=token.is_set)
                if token.is_set():
                    raise OfflineError('cancelled', 'Transfer cancelled before import.')
                preview = TransferStore(repo).preview(raw)
                return raw, preview
            return work
        return self._submit(factory, lambda result: self.view.preview_ready(*result), 'Reading and validating all audits and history...')

    def apply(self, raw, preview):
        def factory(token):
            def work(repo):
                from desktop.offline.transfer_store import TransferStore
                return TransferStore(repo).apply(raw, preview, cancel=token.is_set)
            return work
        return self._submit(factory, self.view.import_finished, 'Importing new audits and recording the receipt. Finishing may already be underway.', operation='import')

    def cancel(self):
        if self.pending:
            self.cancel_event.set()
            self.view.status('Cancellation requested. Waiting for the operation result; a completed import or file save remains confirmed.', True)

def confirm_import(view, confirm_adapter):
    if view.preview_result is None or view.controller.pending: return
    raw,preview=view.raw,view.preview_result
    confirm_adapter(view.app,'Import selected audits?',
            f'Import {len(preview.new_ids)} new audits with complete history?\n'
            f'Skip {len(preview.duplicate_ids)} exact duplicates and {len(preview.conflict_ids)} conflicting audits.\n'
            'Conflicts will not be merged or overwritten. Your local auditor profile remains unchanged.',
            lambda:view.controller.apply(raw,preview),'Import new; skip conflicts' if preview.conflict_ids else 'Import new records only')
