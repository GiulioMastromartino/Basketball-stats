"""Add updated_at to system_settings table

Revision ID: s3tt1ngs_upd4t
Revises: g4m3s_sch3m4
Create Date: 2026-02-24 13:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 's3tt1ngs_upd4t'
down_revision = 'g4m3s_sch3m4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    if 'system_settings' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('system_settings')]
        
        if 'updated_at' not in columns:
            with op.batch_alter_table('system_settings', schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column('updated_at', sa.DateTime(), nullable=True)
                )


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    if 'system_settings' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('system_settings')]
        
        if 'updated_at' in columns:
            with op.batch_alter_table('system_settings', schema=None) as batch_op:
                batch_op.drop_column('updated_at')
