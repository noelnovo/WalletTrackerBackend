"""Server properties: one source of truth for currencies and supported kinds."""
import sqlalchemy as sa

revision = 'd2c100000001'
down_revision = 'd2a100000001'
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    table = sa.Table('AppProperty', sa.MetaData(), sa.Column('key', sa.String(64), primary_key=True),
                     sa.Column('value', sa.JSON, nullable=False), autoload_with=op.get_bind())
    op.get_bind().execute(table.insert(), [
        {'key': 'currencies', 'value': ['EUR', 'USD', 'GBP']},
        {'key': 'record_kinds', 'value': ['category', 'expense', 'bill', 'debt', 'person']},
    ])


def downgrade():
    raise RuntimeError('Destructive property downgrade requires an approved recovery plan')
