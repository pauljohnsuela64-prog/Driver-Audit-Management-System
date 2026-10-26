from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base, UTCDateTime, UTCNow, utcnow


class AdminActivityEvent(Base):
    __tablename__ = "admin_activity_events"
    __table_args__ = (
        CheckConstraint("action IN ('CREATE', 'PROFILE_UPDATE', 'ROLE_CHANGE', 'ACTIVATED', 'DEACTIVATED', 'PASSWORD_RESET', 'PASSWORD_CHANGE')", name="valid_action"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    changes: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=UTCNow(), index=True)
