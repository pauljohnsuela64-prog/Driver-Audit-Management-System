from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base, UTCDateTime, UTCNow, utcnow


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=UTCNow())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, server_default=UTCNow())


class User(Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'AUDITOR')", name="valid_role"),
        CheckConstraint("length(trim(username)) > 0", name="username_nonempty"),
        CheckConstraint("length(trim(full_name)) > 0", name="full_name_nonempty"),
        CheckConstraint("length(password_hash) > 0", name="password_hash_nonempty"),
        CheckConstraint("is_active IN (0, 1)", name="valid_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    audits: Mapped[list["AuditRecord"]] = relationship(back_populates="auditor", foreign_keys="AuditRecord.audited_by_user_id")
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", passive_deletes="all")
    events: Mapped[list["AuditEvent"]] = relationship(back_populates="actor", passive_deletes="all")


class AuditRecord(Timestamps, Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("length(trim(driver_name)) > 0", name="driver_nonempty"),
        CheckConstraint("length(trim(station)) > 0", name="station_nonempty"),
        CheckConstraint("length(trim(plate_number)) > 0", name="plate_nonempty"),
        CheckConstraint("length(trim(audited_by_name)) > 0", name="auditor_nonempty"),
        CheckConstraint("idempotency_key IS NULL OR length(trim(idempotency_key)) > 0", name="key_nonempty"),
        CheckConstraint("(deleted_at IS NULL AND deleted_by_user_id IS NULL) OR (deleted_at IS NOT NULL AND deleted_by_user_id IS NOT NULL)", name="deletion_pair"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    driver_name: Mapped[str] = mapped_column(String(200))
    helper_name: Mapped[str | None] = mapped_column(String(200))
    audit_date: Mapped[date] = mapped_column(Date, index=True)
    station: Mapped[str] = mapped_column(String(150), index=True)
    plate_number: Mapped[str] = mapped_column(String(30), index=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    audited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    audited_by_name: Mapped[str] = mapped_column(String(200))
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    deleted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    auditor: Mapped[User] = relationship(back_populates="audits", foreign_keys=[audited_by_user_id])
    updated_by: Mapped[User | None] = relationship(foreign_keys=[updated_by_user_id])
    deleted_by: Mapped[User | None] = relationship(foreign_keys=[deleted_by_user_id])
    events: Mapped[list["AuditEvent"]] = relationship(back_populates="audit", passive_deletes="all")
    __mapper_args__ = {"version_id_col": version}


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("action IN ('CREATE', 'UPDATE', 'DELETE')", name="valid_action"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audit_records.id", ondelete="RESTRICT"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(10))
    before_data: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    after_data: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=UTCNow(), index=True)
    audit: Mapped[AuditRecord] = relationship(back_populates="events")
    actor: Mapped[User] = relationship(back_populates="events")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="valid_expiry"),
        CheckConstraint("revoked_at IS NULL OR revoked_at >= created_at", name="valid_revocation"),
        CheckConstraint("length(token_hash) = 64", name="token_hash_length"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=UTCNow())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    user: Mapped[User] = relationship(back_populates="sessions")
