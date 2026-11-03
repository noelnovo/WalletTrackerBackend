from unittest import mock
from endpoints.HealthEndpoints import db


def test_readiness_checks_database(client):
    response = client.get('/api/v1/ready')
    assert response.status_code == 200
    assert response.json['success'] is True


def test_readiness_failure_does_not_leak_connection_error(client):
    with mock.patch.object(db.session, 'execute', side_effect=RuntimeError('synthetic-private-credential')):
        response = client.get('/api/v1/ready')
    assert response.status_code == 503
    assert 'synthetic-private-credential' not in response.get_data(as_text=True)
