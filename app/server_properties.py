"""One server-side source of truth for values clients otherwise hardcode.

Missing or broken rows fail safe to code defaults, so a partially migrated
database still serves a valid contract.
"""
from sqlalchemy import select
from models.AppProperty import AppProperty

DEFAULTS = {
    'currencies': ['EUR', 'USD', 'GBP'],
    'record_kinds': ['category', 'expense', 'bill', 'debt', 'person'],
}


def read(session):
    """Return properties as plain lists, ignoring malformed rows."""
    values = dict(DEFAULTS)
    try:
        rows = session.execute(select(AppProperty)).scalars().all()
    except Exception:
        return values
    for row in rows:
        if isinstance(row.value, list) and row.value:
            values[row.key] = row.value
    return values


def currencies(session):
    return [value for value in read(session)['currencies'] if isinstance(value, str)]
