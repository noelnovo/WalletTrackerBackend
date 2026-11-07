"""Add revocable v2 sessions and shared rate limits; preserve v1 identities."""
from alembic import op
import sqlalchemy as sa

revision = 'd2a100000001'
down_revision = 'f19f76872f76'
branch_labels = None
depends_on = None


def upgrade():
    # Existing installations may have INT or BIGINT user IDs. Match the actual FK.
    user_type = next(column['type'] for column in sa.inspect(op.get_bind()).get_columns('User') if column['name'] == 'id')
    op.create_table('ApiSession', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('user_id', user_type, sa.ForeignKey('User.id'), nullable=False),
                    sa.Column('expires', sa.BigInteger(), nullable=False),
                    sa.Column('revoked', sa.Boolean(), nullable=False))
    op.create_index('ix_ApiSession_user_id', 'ApiSession', ['user_id'])
    op.create_table('RefreshGrant', sa.Column('digest', sa.String(64), primary_key=True),
                    sa.Column('session_id', sa.String(36), sa.ForeignKey('ApiSession.id'), nullable=False),
                    sa.Column('used', sa.Boolean(), nullable=False))
    op.create_index('ix_RefreshGrant_session_id', 'RefreshGrant', ['session_id'])
    op.create_table('RateBucket', sa.Column('id', sa.String(64), primary_key=True),
                    sa.Column('hits', sa.Integer(), nullable=False), sa.Column('expires', sa.BigInteger(), nullable=False))
    op.create_index('ix_RateBucket_expires', 'RateBucket', ['expires'])


def downgrade():
    raise RuntimeError('Destructive auth downgrade requires an approved recovery plan')
