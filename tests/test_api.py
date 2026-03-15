import pytest
from datetime import datetime, timedelta


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Сервис сокращения ссылок" in r.json().get("message", "")


def test_shorten_link(client):
    r = client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/long-page"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "short_code" in data
    assert data["original_url"] == "https://example.com/long-page"
    assert "id" in data


def test_shorten_with_custom_alias(client):
    r = client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com",
            "custom_alias": "myalias",
        },
    )
    assert r.status_code == 200
    assert r.json()["short_code"] == "myalias"


def test_shorten_duplicate_alias(client):
    client.post(
        "/links/shorten",
        json={"original_url": "https://a.com", "custom_alias": "dup"},
    )
    r = client.post(
        "/links/shorten",
        json={"original_url": "https://b.com", "custom_alias": "dup"},
    )
    assert r.status_code == 400


def test_redirect(client):
    client.post(
        "/links/shorten",
        json={"original_url": "https://redirect-target.com", "custom_alias": "r1"},
    )
    r = client.get("/links/r1", follow_redirects=False)
    assert r.status_code == 302
    assert "redirect-target.com" in r.headers.get("location", "")


def test_redirect_nonexistent(client):
    r = client.get("/links/nonexistent123")
    assert r.status_code == 404


def test_stats(client):
    client.post(
        "/links/shorten",
        json={"original_url": "https://stats-test.com", "custom_alias": "st1"},
    )
    client.get("/links/st1")
    client.get("/links/st1")
    r = client.get("/links/st1/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["short_code"] == "st1"
    assert data["click_count"] == 2
    assert "created_at" in data
    assert "last_used_at" in data


def test_search_by_url(client):
    client.post(
        "/links/shorten",
        json={"original_url": "https://search-target.com", "custom_alias": "sr1"},
    )
    r = client.get("/links/search", params={"original_url": "https://search-target.com"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert any(l["short_code"] == "sr1" for l in data)


def test_register_and_login(client):
    r = client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "secret123",
        },
    )
    assert r.status_code == 200
    assert r.json()["username"] == "testuser"

    r = client.post(
        "/auth/login",
        json={"username": "testuser", "password": "secret123"},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_update_link_requires_auth(client):
    client.post(
        "/links/shorten",
        json={"original_url": "https://a.com", "custom_alias": "up1"},
    )
    r = client.put(
        "/links/up1",
        json={"original_url": "https://b.com"},
    )
    assert r.status_code == 401


def test_delete_link_requires_auth(client):
    client.post(
        "/links/shorten",
        json={"original_url": "https://a.com", "custom_alias": "del1"},
    )
    r = client.delete("/links/del1")
    assert r.status_code == 401


def test_update_link_as_owner(client):
    client.post(
        "/auth/register",
        json={"username": "owner1", "email": "owner1@x.com", "password": "pass"},
    )
    login = client.post(
        "/auth/login",
        json={"username": "owner1", "password": "pass"},
    )
    token = login.json()["access_token"]

    client.post(
        "/links/shorten",
        json={"original_url": "https://original.com", "custom_alias": "owned"},
        headers={"Authorization": f"Bearer {token}"},
    )
    r = client.put(
        "/links/owned",
        json={"original_url": "https://updated.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["original_url"] == "https://updated.com"


def test_shorten_with_expires_at(client):
    expiry = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    r = client.post(
        "/links/shorten",
        json={
            "original_url": "https://expire-test.com",
            "custom_alias": "exp1",
            "expires_at": expiry,
        },
    )
    assert r.status_code == 200
    assert r.json()["expires_at"] is not None


def test_expired_history(client):
    r = client.get("/links/expired/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_cleanup_unused(client):
    r = client.delete("/links/cleanup/unused", params={"days": 30})
    assert r.status_code == 200
    assert "deleted_count" in r.json()
