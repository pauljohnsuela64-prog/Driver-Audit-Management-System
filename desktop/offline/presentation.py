"""Local view contracts and draft state, independent of Tk and server identity."""
from dataclasses import dataclass, field

from desktop.offline.models import AuditFilter, OfflineError, normalize_values, new_uuid

FIELDS = ('driver_name', 'helper_name', 'audit_date', 'station', 'plate_number', 'remarks')


def record_values(record):
    return {key: getattr(record, key) for key in FIELDS}


def local_filter(query):
    return AuditFilter(driver=query.driver_name, plate=query.plate_number, station=query.station,
                       date_from=query.date_from or None, date_to=query.date_to or None,
                       include_archived=query.include_deleted,
                       sort={'id': 'created', '-id': '-created'}.get(query.sort, query.sort),
                       page=query.page, page_size=query.page_size)


@dataclass(frozen=True)
class AuditView:
    """Aliases needed by the shared read-only views; no server user or session."""
    local: object

    def __getattr__(self, name):
        return getattr(self.local, name)

    @property
    def deleted_at(self):
        return self.local.archived_at

    @property
    def version(self):
        return self.local.revision


def present_audit(record):
    return record if isinstance(record, AuditView) else AuditView(record)


@dataclass(frozen=True)
class CreationIntent:
    key: str
    _values: tuple

    @property
    def payload(self):
        return dict(self._values)


@dataclass
class OfflineDraft:
    values: dict
    baseline: object = None
    intent: CreationIntent | None = None
    pending: bool = False
    uncertain: bool = False
    unavailable: bool = False
    latest: object = None
    message: str = ''
    errors: dict = field(default_factory=dict)

    def creation(self):
        if self.intent is None:
            payload = normalize_values(self.values)
            self.intent = CreationIntent(new_uuid(), tuple(payload.items()))
        return self.intent.key, self.intent.payload

    @property
    def dirty(self):
        if self.pending or self.uncertain:
            return True
        if self.baseline:
            try:
                return normalize_values(self.values) != record_values(self.baseline)
            except OfflineError:
                return True
        return any(value for key, value in self.values.items() if key != 'audit_date')
