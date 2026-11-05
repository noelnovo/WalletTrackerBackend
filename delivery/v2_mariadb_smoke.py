"""Synthetic MariaDB tenant isolation/concurrency proof; never target a live schema."""
import os
import secrets
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor


def run(app):
    if os.environ.get('CI') != 'true' or not os.environ.get('DATABASE_NAME', '').endswith('_ci'):
        raise RuntimeError('Disposable CI database required')
    password = secrets.token_urlsafe(24)
    username = 'ci-v2-' + uuid.uuid4().hex[:12]
    address = f'198.18.{secrets.randbelow(256)}.{secrets.randbelow(254) + 1}'
    with app.test_client() as client:
        client.environ_base['REMOTE_ADDR'] = address
        assert client.post('/api/v2/register', json=dict(username=username, password=password)).status_code == 201
        login = client.post('/api/v2/login', json=dict(username=username, password=password)).get_json()
        header = {'Authorization': 'Bearer ' + login['access_token']}
        record_id = str(uuid.uuid4())
        def operation(name):
            return dict(id=record_id, operation_id=str(uuid.uuid4()), kind='category', base_version=0, deleted=False, payload={'name': name})
        operations = [operation('First writer'), operation('Second writer')]
        def push(op):
            with app.test_client() as thread_client:
                thread_client.environ_base['REMOTE_ADDR'] = address
                response = thread_client.post('/api/v2/sync', headers=header, json={'operations': [op]})
                assert response.status_code == 200
                return response.get_json()['results'][0]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(push, operations))
        assert sorted(result['status'] for result in results) == ['applied', 'conflict']
        for op, result in zip(operations, results):
            assert push(op) == result
        page = client.get('/api/v2/sync?limit=1', headers=header).get_json()
        assert len(page['records']) == 1 and not page['has_more']
        # A second independently provisioned account must not see the first tenant.
        other = username + '-other'
        assert client.post('/api/v2/register', json=dict(username=other, password=password)).status_code == 201
        other_login = client.post('/api/v2/login', json=dict(username=other, password=password)).get_json()
        other_page = client.get('/api/v2/sync', headers={'Authorization': 'Bearer ' + other_login['access_token']}).get_json()
        assert other_page['records'] == []
        barrier = threading.Barrier(2)
        def refresh(_):
            with app.test_client() as thread_client:
                thread_client.environ_base['REMOTE_ADDR'] = address
                barrier.wait(timeout=10)
                response = thread_client.post('/api/v2/refresh', json={'refresh_token': login['refresh_token']})
                return response.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(refresh, range(2)))
        assert statuses == [200, 401], f'Concurrent refresh statuses: {statuses}'
        assert client.get('/api/v2/sync', headers=header).status_code == 401
    print('Real MariaDB v2 concurrent conflict, idempotency, tenant isolation and refresh replay passed')
