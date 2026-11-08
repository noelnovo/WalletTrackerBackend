import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from db import db
from models.Sync import SyncClock, SyncRecord, SyncReceipt
import endpoints.V2Sync as sync_module


def uid():
    return str(uuid.uuid4())


@pytest.fixture
def v2(app, client, tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path}/tenant.db')
    db.metadata.create_all(engine, tables=[SyncClock.__table__, SyncRecord.__table__, SyncReceipt.__table__])
    factory = scoped_session(sessionmaker(bind=engine))
    factory.add(SyncClock(id=1, revision=0))
    factory.commit()
    factory.remove()
    monkeypatch.setattr(sync_module, 'get_tenant_session', lambda user: factory)
    app.config['RATE_LIMIT_DISABLED'] = True
    response = client.post('/api/v2/login', json=dict(username='testuser', password='password123'))
    assert response.status_code == 200
    tokens = response.get_json()
    yield client, {'Authorization': f'Bearer {tokens["access_token"]}'}, tokens
    factory.remove()
    engine.dispose()


def operation(kind='category', **changes):
    result = dict(operation_id=uid(), id=uid(), kind=kind, base_version=0, deleted=False, payload={'name': 'Food'})
    result.update(changes)
    return result


def test_sync_retry_conflict_and_pagination(v2):
    client, headers, _ = v2
    op = operation()
    def push(item):
        return client.post('/api/v2/sync', headers=headers, json={'operations': [item]})
    first = push(op).get_json()
    assert first['results'][0]['status'] == 'applied'
    assert push(op).get_json() == first
    stale = dict(op, operation_id=uid(), payload={'name': 'Stale'})
    assert push(stale).get_json()['results'][0]['status'] == 'conflict'
    assert push(dict(op, payload={'name': 'Reused id'})).status_code == 400
    push(operation())
    page = client.get('/api/v2/sync?limit=1', headers=headers).get_json()
    assert page['has_more'] and len(page['records']) == 1
    next_page = client.get(f'/api/v2/sync?cursor={page["cursor"]}&limit=1', headers=headers).get_json()
    assert not next_page['has_more'] and len(next_page['records']) == 1
    assert client.get('/api/v2/sync?limit=201', headers=headers).status_code == 400


def test_delete_tombstone_and_conflicting_restore(v2):
    client, headers, _ = v2
    op = operation()
    def push(item):
        return client.post('/api/v2/sync', headers=headers, json={'operations': [item]}).get_json()['results'][0]
    push(op)
    deleted = push(dict(op, operation_id=uid(), base_version=1, deleted=True))
    assert deleted['record']['deleted']
    assert push(dict(op, operation_id=uid(), base_version=1))['status'] == 'conflict'
    assert push(dict(op, operation_id=uid(), base_version=2))['record']['version'] == 3


def test_exact_bill_shares_and_validation(v2):
    client, headers, _ = v2
    payload = dict(amount_minor=1000, currency='EUR', date='2026-11-05', description='Dinner', participants=['A', 'B', 'C'], paid_by='A')
    result = client.post('/api/v2/sync', headers=headers, json={'operations': [operation('bill', payload=payload)]})
    assert result.status_code == 200
    shares = result.get_json()['results'][0]['record']['payload']['shares']
    assert [share['amount_minor'] for share in shares] == [334, 333, 333]
    invalid = dict(payload, amount_minor=True)
    assert client.post('/api/v2/sync', headers=headers, json={'operations': [operation('bill', payload=invalid)]}).status_code == 400


def test_assigned_extras_survive_push_retry_and_pull(v2):
    client, headers, _ = v2
    payload = dict(amount_minor=1500, currency='EUR', date='2026-11-05', description='Dinner',
                   participants=['Alex', 'Sam'], paid_by='Sam',
                   extras=[dict(description='Wine', amount_minor=500, participant='Alex')],
                   shares=[dict(name='Alex', amount_minor=1)])  # Client totals are never trusted.
    op = operation('bill', payload=payload)
    first = client.post('/api/v2/sync', headers=headers, json={'operations': [op]})
    assert first.status_code == 200
    result = first.get_json()
    stored = result['results'][0]['record']['payload']
    assert [share['amount_minor'] for share in stored['shares']] == [1000, 500]
    assert stored['paid_by'] == 'Sam'
    assert stored['extras'] == payload['extras']
    assert client.post('/api/v2/sync', headers=headers, json={'operations': [op]}).get_json() == result
    assert client.get('/api/v2/sync', headers=headers).get_json()['records'][0]['payload'] == stored


def test_split_rounding_optional_extra_names_and_zero_remainder(v2):
    client, headers, _ = v2
    payload = dict(amount_minor=1001, currency='EUR', date='2026-11-05', description='Dinner',
                   participants=['A', 'B', 'C'], paid_by='A',
                   extras=[dict(amount_minor=100, participant='C')])
    response = client.post('/api/v2/sync', headers=headers, json={'operations': [operation('bill', payload=payload)]})
    stored = response.get_json()['results'][0]['record']['payload']
    assert [share['amount_minor'] for share in stored['shares']] == [301, 300, 400]
    assert stored['extras'][0]['description'] == ''
    payload.update(amount_minor=100, extras=[dict(amount_minor=100, participant='A')])
    response = client.post('/api/v2/sync', headers=headers, json={'operations': [operation('bill', payload=payload)]})
    assert [share['amount_minor'] for share in response.get_json()['results'][0]['record']['payload']['shares']] == [100, 0, 0]


@pytest.mark.parametrize('extras', [
    None, {}, ['invalid'], [dict(amount_minor=True, participant='A')],
    [dict(amount_minor=0, participant='A')], [dict(amount_minor=-1, participant='A')],
    [dict(amount_minor=1001, participant='A')], [dict(amount_minor=1.5, participant='A')],
    [dict(amount_minor=700, participant='A'), dict(amount_minor=301, participant='B')],
    [dict(amount_minor=100, participant='Unknown')],
    [dict(amount_minor=100, participant='A', description=123)],
    [dict(amount_minor=100, participant='A', description='X' * 81)],
    [dict(amount_minor=1, participant='A')] * 101,
])
def test_invalid_extras_are_rejected_without_records(v2, extras):
    client, headers, _ = v2
    payload = dict(amount_minor=1000, currency='EUR', date='2026-11-05', description='Dinner',
                   participants=['A', 'B'], paid_by='A', extras=extras)
    response = client.post('/api/v2/sync', headers=headers, json={'operations': [operation('bill', payload=payload)]})
    assert response.status_code == 400
    assert client.get('/api/v2/sync', headers=headers).get_json()['records'] == []


def test_duplicate_names_ignore_case_and_whitespace(v2):
    client, headers, _ = v2
    payload = dict(amount_minor=1000, currency='EUR', date='2026-11-05', description='Dinner',
                   participants=['Alex', ' alex '], paid_by='Alex')
    assert client.post('/api/v2/sync', headers=headers, json={'operations': [operation('bill', payload=payload)]}).status_code == 400


def test_refresh_rotation_replay_and_logout(v2):
    client, headers, tokens = v2
    refreshed = client.post('/api/v2/refresh', json={'refresh_token': tokens['refresh_token']})
    assert refreshed.status_code == 200
    assert refreshed.get_json()['refresh_token'] != tokens['refresh_token']
    assert client.post('/api/v2/refresh', json={'refresh_token': tokens['refresh_token']}).status_code == 401
    assert client.get('/api/v2/sync', headers=headers).status_code == 401
    login = client.post('/api/v2/login', json=dict(username='testuser', password='password123')).get_json()
    fresh_headers = {'Authorization': f'Bearer {login["access_token"]}'}
    assert client.post('/api/v2/logout', headers=fresh_headers).status_code == 200
    assert client.get('/api/v2/sync', headers=fresh_headers).status_code == 401


def test_rate_limit_shared_and_forwarded_header_not_trusted(app, client):
    app.config['RATE_LIMIT_DISABLED'] = False
    for i in range(10):
        assert client.post('/api/v2/login', json={}, headers={'X-Forwarded-For': f'192.0.2.{i}'}).status_code == 401
    response = client.post('/api/v2/login', json={})
    assert response.status_code == 429
    assert int(response.headers['Retry-After']) > 0
    assert response.headers['Cache-Control'] == 'no-store'


def test_registration_default_disabled(app, client):
    assert client.post('/api/v2/register', json={}).status_code == 403


def test_unauthenticated_sync(client):
    assert client.get('/api/v2/sync').status_code == 401


@pytest.mark.parametrize('address', ['203.0.113.1', '192.168.1.246', '10.2.0.13'])
def test_client_network_does_not_replace_authentication(v2, address):
    client, headers, _ = v2
    peer = {'REMOTE_ADDR': address}
    assert client.get('/api/v2/sync', environ_base=peer).status_code == 401
    assert client.get('/api/v2/sync', environ_base=peer, headers=headers).status_code == 200


def test_trusted_proxy_identifies_separate_rate_limit_clients(app, client):
    app.config.update(TRUSTED_PROXY_NETWORKS=['10.2.0.10/32'], RATE_LIMIT_DISABLED=False)
    peer = {'REMOTE_ADDR': '10.2.0.10'}
    for _ in range(10):
        assert client.post('/api/v2/login', json={}, environ_base=peer, headers={'X-Forwarded-For': '203.0.113.1'}).status_code == 401
    assert client.post('/api/v2/login', json={}, environ_base=peer, headers={'X-Forwarded-For': '203.0.113.1'}).status_code == 429
    assert client.post('/api/v2/login', json={}, environ_base=peer, headers={'X-Forwarded-For': '203.0.113.2'}).status_code == 401


def test_dev_v1_write_guard_remains_enabled(client, monkeypatch):
    monkeypatch.setenv('WALLET_TRACKER_V2_ONLY', 'true')
    assert client.post('/api/v1/login/', json={}).status_code == 410
    assert client.get('/api/v1/health').status_code == 200
    assert client.get('/api/v2/sync').status_code == 401


def test_invalid_json_shapes_are_rejected(v2):
    client, headers, _ = v2
    assert client.post('/api/v2/login', json=['not-an-object']).status_code == 401
    assert client.post('/api/v2/refresh', json=['not-an-object']).status_code == 401
    assert client.post('/api/v2/sync', headers=headers, json=['not-an-object']).status_code == 400
