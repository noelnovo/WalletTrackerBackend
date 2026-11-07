"""Server-only registration policy; disposable SQLite fixture, no account provisioning."""
from unittest.mock import patch


def test_registration_authorization_can_change_without_changing_the_client(app, client):
    app.config['RATE_LIMIT_DISABLED'] = True
    payload = {'username': 'x', 'password': 'x'}
    with patch('endpoints.V2Auth.UserRepository.create_with_password') as create_account:
        app.config['ENABLE_REGISTER'] = False
        assert client.post('/api/v2/register', json=payload).status_code == 403
        app.config['ENABLE_REGISTER'] = True
        # The same request now reaches normal validation, not account creation.
        assert client.post('/api/v2/register', json=payload).status_code == 400
        app.config['ENABLE_REGISTER'] = False
        assert client.post('/api/v2/register', json=payload).status_code == 403
        create_account.assert_not_called()


def test_enabled_registration_reaches_provisioning_only_with_server_permission(app, client):
    app.config['RATE_LIMIT_DISABLED'] = True
    payload = {'username': 'registration-fixture', 'password': 'synthetic-fixture-only'}
    with patch('endpoints.V2Auth.UserRepository.create_with_password') as create_account, \
            patch('endpoints.V2Auth.create_tenant_user_and_db') as provision:
        app.config['ENABLE_REGISTER'] = False
        assert client.post('/api/v2/register', json=payload).status_code == 403
        create_account.assert_not_called()
        provision.assert_not_called()
        app.config['ENABLE_REGISTER'] = True
        response = client.post('/api/v2/register', json=payload)
        assert response.status_code == 201
        assert response.get_json() == {'registered': True}
        create_account.assert_called_once()
        provision.assert_called_once()
        app.config['ENABLE_REGISTER'] = False
        assert client.post('/api/v2/register', json=payload).status_code == 403
        assert create_account.call_count == provision.call_count == 1
