from unittest.mock import patch
from utils.Constants import AuthMessages, UserMessages


@patch("endpoints.AuthenticationEndpoints.create_tenant_user_and_db")
def test_register_success(mock_create_tenant, client):
    mock_create_tenant.return_value = ("test_user", "test_pass")

    response = client.post("/api/v1/register/", json={
        "username": "newuser",
        "password": "securepass1"
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["message"] == UserMessages.CREATED
    assert "id" in data["data"]
    assert data["data"]["username"] == "newuser"
    assert set(data["data"]) == {"id", "username"}


def test_register_duplicate_username(client):
    response = client.post("/api/v1/register/", json={
        "username": "testuser",
        "password": "irrelevant"
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is False
    assert data["message"] == AuthMessages.ALREADY_EXISTS


def test_register_missing_username(client):
    response = client.post("/api/v1/register/", json={
        "password": "securepass1"
    })

    assert response.status_code == 400


def test_register_missing_password(client):
    response = client.post("/api/v1/register/", json={
        "username": "anotheruser"
    })

    assert response.status_code == 400
