"""Optimistic, idempotent synchronization against isolated tenant databases."""
import hashlib
import json
import uuid
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
    result = dict(amount_minor=amount, currency=currency, date=day,
                  description=label(payload.get('description')))
    if kind == 'expense':
        category_id = identifier(payload.get('category_id'))
        category = session.get(SyncRecord, category_id)
        if not category or category.kind != 'category' or category.deleted:
            raise ValueError('Choose an active category')
        result['category_id'] = category_id
    else:
        participants = payload.get('participants')
        if not isinstance(participants, list) or not 2 <= len(participants) <= 100:
            raise ValueError('A bill needs 2–100 people')
        participants = [label(person, 80) for person in participants]
        if len(set(participants)) != len(participants):
            raise ValueError('Use unique participant names')
        paid_by = label(payload.get('paid_by'), 80)
        if paid_by not in participants:
            raise ValueError('The payer must be a participant')
        share, remainder = divmod(amount, len(participants))
        result.update(participants=participants, paid_by=paid_by,
                      shares=[dict(name=person, amount_minor=share + int(i < remainder)) for i, person in enumerate(participants)])
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
    results = []
    try:
        # A tenant-local clock serializes writers and gives a commit-ordered cursor.
        clock = session.execute(select(SyncClock).where(SyncClock.id == 1).with_for_update()).scalar_one()
        for operation in operations:
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
            receipt = session.get(SyncReceipt, operation_id)
            if receipt:
                if receipt.digest != fingerprint:
                    raise ValueError('Operation id reused with different content')
                results.append(receipt.result)
                continue
            row = session.get(SyncRecord, record_id)
            if (row.version if row else 0) != expected or (row and row.kind != kind):
                result = dict(operation_id=operation_id, status='conflict', remote=row.public() if row else None)
            else:
                if deleted and kind == 'category':
                    # Do not silently cascade-delete expenses, including offline ones.
                    expense = session.execute(select(SyncRecord.id).where(SyncRecord.kind == 'expense', SyncRecord.deleted.is_(False), SyncRecord.payload['category_id'].as_string() == record_id).limit(1)).first()
                    if expense:
                        raise ValueError('Move or delete category expenses first')
                payload = row.payload if deleted and row else ({} if deleted else validate_payload(kind, operation.get('payload'), session))
                clock.revision += 1
                if not row:
                    row = SyncRecord(id=record_id, kind=kind)
                    session.add(row)
                row.version = expected + 1
                row.revision = clock.revision
                row.deleted = deleted
                row.payload = payload
                session.flush()
                result = dict(operation_id=operation_id, status='applied', record=row.public())
            session.add(SyncReceipt(id=operation_id, digest=fingerprint, result=result))
            session.flush()
            results.append(result)
        session.commit()
        return jsonify(results=results)
    except (ValueError, TypeError, AttributeError) as error:
        session.rollback()
        return jsonify(error=str(error)), 400
    finally:
        session.remove()
