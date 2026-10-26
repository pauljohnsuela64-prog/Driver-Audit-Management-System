"""Server-controlled, secret-free account event construction."""
from backend.models import AdminActivityEvent

FIELDS = {
    "CREATE": ("username", "full_name", "role", "is_active"),
    "PROFILE_UPDATE": ("username", "full_name"),
    "ROLE_CHANGE": ("role",),
    "ACTIVATED": ("is_active",),
    "DEACTIVATED": ("is_active",),
    "PASSWORD_RESET": (),
    "PASSWORD_CHANGE": (),
}


def write_activity(session, actor_id, target, action, before=None):
    before = before or {}
    changes = {field: {"before": before.get(field), "after": getattr(target, field)}
               for field in FIELDS[action]
               if (action == "CREATE" or field in before) and before.get(field) != getattr(target, field)}
    if not changes and action in {"PROFILE_UPDATE", "ROLE_CHANGE", "ACTIVATED", "DEACTIVATED"}:
        return
    session.add(AdminActivityEvent(actor_user_id=actor_id, target_user_id=target.id,
                                  action=action, changes=changes or None))
    session.flush()
