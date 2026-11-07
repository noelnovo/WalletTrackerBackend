"""Optimistic, idempotent synchronization against isolated tenant databases."""
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from flask import Blueprint, g, jsonify, request
from sqlalchemy import select
from endpoints.V2Auth import authenticated, json_object
from models.Sync import SyncClock, SyncRecord, SyncReceipt
from utils.Multitenant import get_tenant_session

v2sync = Blueprint('v2sync', __name__, url_prefix='/api/v2')


def identifier(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('Expected a canonical UUID')
    return value


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Integer outside allowed range')
    return value


def label(value, maximum=255):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('Missing or too long text')
    return value.strip()


def validate_payload(kind, payload, session):
    if not isinstance(payload, dict):
        raise ValueError('Expected an object payload')
    if kind == 'category':
        return {'name': label(payload.get('name'), 80)}
    if kind not in ('expense', 'bill'):
        raise ValueError('Unknown record kind')
    amount = integer(payload.get('amount_minor'), 1, 99999999999)
    currency = payload.get('currency', 'EUR')
    if currency not in ('EUR', 'USD', 'GBP'):
        raise ValueError('Unsupported currency')
    day = payload.get('date')
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError('Expected ISO date')
    result = {'amount_minor': amount, 'currency': currency, 'date': day,
              'description': label(payload.get('description'))}
    if kind == 'expense':
        result['category_id'] = category_reference(payload.get('category_id'), session)
    else:
        result.update(bill_split(payload, amount))
    return result


def category_reference(value, session):
    category_id = identifier(value)
    category = session.get(SyncRecord, category_id)
    if not category or category.kind != 'category' or category.deleted:
        raise ValueError('Choose an active category')
    return category_id


def bill_split(payload, amount):
    participants = payload.get('participants')
    if not isinstance(participants, list) or not 2 <= len(participants) <= 100:
        raise ValueError('A bill needs 2–100 people')
    participants = [label(person, 80) for person in participants]
    if len({person.lower() for person in participants}) != len(participants):
        raise ValueError('Use unique participant names')
    paid_by = label(payload.get('paid_by'), 80)
    if paid_by not in participants:
        raise ValueError('The payer must be a participant')
    extras = payload.get('extras', [])
    if not isinstance(extras, list) or len(extras) > 100:
        raise ValueError('Use at most 100 extras')
    normalized_extras = []
    assigned = {person: 0 for person in participants}
    extras_total = 0
    for extra in extras:
        if not isinstance(extra, dict):
            raise ValueError('Expected an extra object')
        description = extra.get('description', '')
        if not isinstance(description, str) or len(description) > 80:
            raise ValueError('Extra names must be at most 80 characters')
        cost = integer(extra.get('amount_minor'), 1, amount)
        person = label(extra.get('participant'), 80)
        if person not in assigned:
            raise ValueError('Choose who had each extra')
        extras_total += cost
        if extras_total > amount:
            raise ValueError('Extras cannot exceed the bill total')
        assigned[person] += cost
        normalized_extras.append({'description': description.strip(), 'amount_minor': cost, 'participant': person})
    share, remainder = divmod(amount - extras_total, len(participants))
    return {'participants': participants, 'paid_by': paid_by,
            'extras': normalized_extras,
            'shares': [{'name': person, 'amount_minor': share + int(i < remainder) + assigned[person]}
                       for i, person in enumerate(participants)]}


@dataclass(frozen=True)
class Mutation:
    operation_id: str
    record_id: str
    expected: int
    kind: str
    deleted: bool
    payload: object
    fingerprint: str


def validate_mutation(operation):
    if not isinstance(operation, dict):
        raise ValueError('Invalid operation')
    operation_id = identifier(operation.get('operation_id'))
    record_id = identifier(operation.get('id'))
    expected = integer(operation.get('base_version'), 0, 2**31 - 1)
    kind = operation.get('kind')
    deleted = operation.get('deleted', False)
    if kind not in ('category', 'expense', 'bill') or type(deleted) is not bool:
        raise ValueError('Invalid kind or deleted flag')
    fingerprint = hashlib.sha256(json.dumps(operation, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return Mutation(operation_id, record_id, expected, kind, deleted, operation.get('payload'), fingerprint)


def ensure_category_empty(session, record_id):
    expense = session.execute(select(SyncRecord.id).where(SyncRecord.kind == 'expense', SyncRecord.deleted.is_(False), SyncRecord.payload['category_id'].as_string() == record_id).limit(1)).first()
    if expense:
        raise ValueError('Move or delete category expenses first')


def write_record(session, clock, mutation, row):
    if mutation.deleted and mutation.kind == 'category':
        ensure_category_empty(session, mutation.record_id)
    if mutation.deleted:
        payload = row.payload if row else {}
    else:
        payload = validate_payload(mutation.kind, mutation.payload, session)
    clock.revision += 1
    if not row:
        row = SyncRecord(id=mutation.record_id, kind=mutation.kind)
        session.add(row)
    row.version = mutation.expected + 1
    row.revision = clock.revision
    row.deleted = mutation.deleted
    row.payload = payload
    session.flush()
    return {'operation_id': mutation.operation_id, 'status': 'applied', 'record': row.public()}


def apply_mutation(session, clock, operation):
    mutation = validate_mutation(operation)
    receipt = session.get(SyncReceipt, mutation.operation_id)
    if receipt:
        if receipt.digest != mutation.fingerprint:
            raise ValueError('Operation id reused with different content')
        return receipt.result
    row = session.get(SyncRecord, mutation.record_id)
    current_version = row.version if row else 0
    if current_version != mutation.expected or (row and row.kind != mutation.kind):
        result = {'operation_id': mutation.operation_id, 'status': 'conflict', 'remote': row.public() if row else None}
    else:
        result = write_record(session, clock, mutation, row)
    session.add(SyncReceipt(id=mutation.operation_id, digest=mutation.fingerprint, result=result))
    session.flush()
    return result


@v2sync.get('/sync')
@authenticated
def pull():
    try:
        cursor = integer(int(request.args.get('cursor', '0')), 0, 2**63 - 1)
        limit = integer(int(request.args.get('limit', '100')), 1, 200)
    except (ValueError, TypeError):
        return jsonify(error='Invalid cursor or limit (1–200)'), 400
    session = get_tenant_session(g.user)
    try:
        clock = session.get(SyncClock, 1)
        upper = clock.revision
        if cursor > upper:
            return jsonify(error='Cursor ahead of server; resync required'), 409
        rows = session.execute(select(SyncRecord).where(SyncRecord.revision > cursor, SyncRecord.revision <= upper).order_by(SyncRecord.revision).limit(limit + 1)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = page[-1].revision if has_more else upper
        return jsonify(records=[row.public() for row in page], cursor=next_cursor, has_more=has_more)
    finally:
        session.remove()


@v2sync.post('/sync')
@authenticated
def push():
    data = json_object()
    operations = data.get('operations')
    if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
        return jsonify(error='Provide 1–100 operations'), 400
    session = get_tenant_session(g.user)
    try:
        # A tenant-local clock serializes writers and gives a commit-ordered cursor.
        clock = session.execute(select(SyncClock).where(SyncClock.id == 1).with_for_update()).scalar_one()
        results = [apply_mutation(session, clock, operation) for operation in operations]
        session.commit()
        return jsonify(results=results)
    except (ValueError, TypeError, AttributeError) as error:
        session.rollback()
        return jsonify(error=str(error)), 400
    finally:
        session.remove()
