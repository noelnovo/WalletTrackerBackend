"""Add versioned finance records and copy legacy expenses without deleting tables."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import uuid
from alembic import op
import sqlalchemy as sa

revision = 'd2b100000001'
down_revision = 'c34bd55b3ea7'
branch_labels = None
depends_on = None


def upgrade():
    clock = op.create_table('SyncClock', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('revision', sa.BigInteger(), nullable=False))
    records = op.create_table('SyncRecord', sa.Column('id', sa.String(36), primary_key=True),
                              sa.Column('kind', sa.String(16), nullable=False), sa.Column('version', sa.Integer(), nullable=False),
                              sa.Column('revision', sa.BigInteger(), nullable=False, unique=True),
                              sa.Column('deleted', sa.Boolean(), nullable=False), sa.Column('payload', sa.JSON(), nullable=False))
    op.create_index('ix_SyncRecord_kind', 'SyncRecord', ['kind'])
    op.create_table('SyncReceipt', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('digest', sa.String(64), nullable=False), sa.Column('result', sa.JSON(), nullable=False))
    connection = op.get_bind()
    revision_number = 0
    category_ids = {}
    for row in connection.execute(sa.text('SELECT id, name FROM ExpenseCategory ORDER BY id')).mappings():
        category_ids[row['id']] = str(uuid.uuid5(uuid.NAMESPACE_URL, f'wallettracker:category:{row["id"]}'))
        revision_number += 1
        connection.execute(records.insert().values(id=category_ids[row['id']], kind='category', version=1, revision=revision_number, deleted=False, payload={'name': row['name']}))
    for row in connection.execute(sa.text('SELECT id, price, description, expenseDate, category FROM Expense ORDER BY id')).mappings():
        revision_number += 1
        amount = int((Decimal(str(row['price'])) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        connection.execute(records.insert().values(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'wallettracker:expense:{row["id"]}')), kind='expense', version=1, revision=revision_number, deleted=False,
                           payload=dict(amount_minor=amount, currency='EUR', description=row['description'] or 'Expense', date=str(row['expenseDate'])[:10], category_id=category_ids[row['category']])))
    connection.execute(clock.insert().values(id=1, revision=revision_number))


def downgrade():
    raise RuntimeError('Finance downgrade would lose sync history; approved recovery required')
