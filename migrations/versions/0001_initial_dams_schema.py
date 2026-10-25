"""initial DAMS schema"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement


class MigrationUTCNow(FunctionElement):
    type = sa.DateTime()
    inherit_cache = True


@compiles(MigrationUTCNow)
def compile_now(element, compiler, **kwargs):
    return "CURRENT_TIMESTAMP"


@compiles(MigrationUTCNow, "mysql")
def compile_mysql_now(element, compiler, **kwargs):
    return "CURRENT_TIMESTAMP(6)"

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Frozen initial schema; independent of application model imports.
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), server_default=MigrationUTCNow(), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), server_default=MigrationUTCNow(), nullable=False),
    sa.CheckConstraint("role IN ('ADMIN', 'AUDITOR')", name=op.f('ck_users_valid_role')),
    sa.CheckConstraint('is_active IN (0, 1)', name=op.f('ck_users_valid_active')),
    sa.CheckConstraint('length(password_hash) > 0', name=op.f('ck_users_password_hash_nonempty')),
    sa.CheckConstraint('length(trim(full_name)) > 0', name=op.f('ck_users_full_name_nonempty')),
    sa.CheckConstraint('length(trim(username)) > 0', name=op.f('ck_users_username_nonempty')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('username', name=op.f('uq_users_username')),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_table('audit_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('driver_name', sa.String(length=200), nullable=False),
    sa.Column('helper_name', sa.String(length=200), nullable=True),
    sa.Column('audit_date', sa.Date(), nullable=False),
    sa.Column('station', sa.String(length=150), nullable=False),
    sa.Column('plate_number', sa.String(length=30), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('audited_by_user_id', sa.Integer(), nullable=False),
    sa.Column('audited_by_name', sa.String(length=200), nullable=False),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('deleted_by_user_id', sa.Integer(), nullable=True),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), server_default=MigrationUTCNow(), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), server_default=MigrationUTCNow(), nullable=False),
    sa.CheckConstraint('(deleted_at IS NULL AND deleted_by_user_id IS NULL) OR (deleted_at IS NOT NULL AND deleted_by_user_id IS NOT NULL)', name=op.f('ck_audit_records_deletion_pair')),
    sa.CheckConstraint('idempotency_key IS NULL OR length(trim(idempotency_key)) > 0', name=op.f('ck_audit_records_key_nonempty')),
    sa.CheckConstraint('length(trim(audited_by_name)) > 0', name=op.f('ck_audit_records_auditor_nonempty')),
    sa.CheckConstraint('length(trim(driver_name)) > 0', name=op.f('ck_audit_records_driver_nonempty')),
    sa.CheckConstraint('length(trim(plate_number)) > 0', name=op.f('ck_audit_records_plate_nonempty')),
    sa.CheckConstraint('length(trim(station)) > 0', name=op.f('ck_audit_records_station_nonempty')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_audit_records_positive_version')),
    sa.ForeignKeyConstraint(['audited_by_user_id'], ['users.id'], name=op.f('fk_audit_records_audited_by_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['deleted_by_user_id'], ['users.id'], name=op.f('fk_audit_records_deleted_by_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_audit_records_updated_by_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_records')),
    sa.UniqueConstraint('idempotency_key', name=op.f('uq_audit_records_idempotency_key')),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_audit_records_audit_date'), 'audit_records', ['audit_date'], unique=False)
    op.create_index(op.f('ix_audit_records_audited_by_user_id'), 'audit_records', ['audited_by_user_id'], unique=False)
    op.create_index(op.f('ix_audit_records_deleted_at'), 'audit_records', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_audit_records_deleted_by_user_id'), 'audit_records', ['deleted_by_user_id'], unique=False)
    op.create_index(op.f('ix_audit_records_plate_number'), 'audit_records', ['plate_number'], unique=False)
    op.create_index(op.f('ix_audit_records_station'), 'audit_records', ['station'], unique=False)
    op.create_index(op.f('ix_audit_records_updated_by_user_id'), 'audit_records', ['updated_by_user_id'], unique=False)
    op.create_table('auth_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), server_default=MigrationUTCNow(), nullable=False),
    sa.Column('expires_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('revoked_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.CheckConstraint('expires_at > created_at', name=op.f('ck_auth_sessions_valid_expiry')),
    sa.CheckConstraint('length(token_hash) = 64', name=op.f('ck_auth_sessions_token_hash_length')),
    sa.CheckConstraint('revoked_at IS NULL OR revoked_at >= created_at', name=op.f('ck_auth_sessions_valid_revocation')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_sessions_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_auth_sessions_token_hash')),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_auth_sessions_expires_at'), 'auth_sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'], unique=False)
    op.create_table('audit_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('audit_id', sa.Integer(), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=10), nullable=False),
    sa.Column('before_data', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('after_data', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), server_default=MigrationUTCNow(), nullable=False),
    sa.CheckConstraint("action IN ('CREATE', 'UPDATE', 'DELETE')", name=op.f('ck_audit_events_valid_action')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_events_actor_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['audit_id'], ['audit_records.id'], name=op.f('fk_audit_events_audit_id_audit_records'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events')),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_audit_events_actor_user_id'), 'audit_events', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_audit_events_audit_id'), 'audit_events', ['audit_id'], unique=False)
    op.create_index(op.f('ix_audit_events_created_at'), 'audit_events', ['created_at'], unique=False)


def downgrade():
    # Drop dependent tables first. MySQL rejects dropping an index still used
    # by a foreign key; dropping its table removes both constraints and indexes.
    op.drop_table('audit_events')
    op.drop_table('auth_sessions')
    op.drop_table('audit_records')
    op.drop_table('users')
