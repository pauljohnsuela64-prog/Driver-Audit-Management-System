"""Dedicated account activity history; existing tables are untouched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


class ActivityUTCNow(FunctionElement):
    type = sa.DateTime()
    inherit_cache = True


@compiles(ActivityUTCNow)
def utc_now(element, compiler, **kwargs):
    return "CURRENT_TIMESTAMP"


@compiles(ActivityUTCNow, "mysql")
def mysql_utc_now(element, compiler, **kwargs):
    return "CURRENT_TIMESTAMP(6)"


def upgrade():
    op.create_table("admin_activity_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("changes", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), server_default=ActivityUTCNow(), nullable=False),
        sa.CheckConstraint("action IN ('CREATE', 'PROFILE_UPDATE', 'ROLE_CHANGE', 'ACTIVATED', 'DEACTIVATED', 'PASSWORD_RESET', 'PASSWORD_CHANGE')", name="valid_action"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4")
    for column in ["actor_user_id", "target_user_id", "action", "created_at"]:
        op.create_index(f"ix_admin_activity_events_{column}", "admin_activity_events", [column])


def downgrade():
    # Drop only this revision's table; never drop FK indexes independently on MySQL.
    op.drop_table("admin_activity_events")
