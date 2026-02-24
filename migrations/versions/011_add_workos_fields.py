"""Add WorkOS fields to User model

Revision ID: 011_add_workos_fields
Revises: 010_add_reb_conceded
Create Date: 2026-02-24 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = "011_add_workos_fields"
down_revision = "010_add_reb_conceded"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]

    with op.batch_alter_table('users', schema=None) as batch_op:
        # Add workos_id for WorkOS authentication
        if 'workos_id' not in columns:
            batch_op.add_column(sa.Column('workos_id', sa.String(length=255), nullable=True))
        
        # Add email_verified flag
        if 'email_verified' not in columns:
            batch_op.add_column(sa.Column('email_verified', sa.Boolean(), server_default='0', nullable=True))
        
        # Make password_hash nullable for WorkOS users
        if 'password_hash' in columns:
            batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=True)

    # Create unique index on workos_id
    try:
        op.create_index('ix_users_workos_id', 'users', ['workos_id'], unique=True)
    except Exception:
        pass  # Index may already exist


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]

    # Drop index first
    try:
        op.drop_index('ix_users_workos_id', table_name='users')
    except Exception:
        pass

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'email_verified' in columns:
            batch_op.drop_column('email_verified')
        
        if 'workos_id' in columns:
            batch_op.drop_column('workos_id')
