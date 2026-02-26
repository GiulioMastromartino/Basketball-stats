"""Add schema_version to games table

Revision ID: g4m3s_sch3m4
Revises: w0rk0s_f13lds
Create Date: 2026-02-24 11:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'g4m3s_sch3m4'
down_revision = 'w0rk0s_f13lds'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    if 'games' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('games')]
        
        if 'schema_version' not in columns:
            with op.batch_alter_table('games', schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column('schema_version', sa.Integer(), server_default='1', nullable=True)
                )


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    if 'games' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('games')]
        
        if 'schema_version' in columns:
            with op.batch_alter_table('games', schema=None) as batch_op:
                batch_op.drop_column('schema_version')
