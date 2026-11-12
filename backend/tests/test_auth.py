from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import FakeLLMProvider


def _auth_settings(tmp_path: Path, *, required: bool = True) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        upload_dir=tmp_path / "uploads",
        llm_provider="offline",
        embedding_provider="offline",
        auth_required=required,
        auth_pbkdf2_iterations=100_000,
    )


def _register(client: TestClient, username: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secreto123", "display_name": username.title()},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_is_required_and_workspaces_are_isolated(tmp_path):
    app = create_app(settings=_auth_settings(tmp_path), provider=FakeLLMProvider())
    with TestClient(app) as client:
        assert client.get("/api/workspaces").status_code == 401

        alice = _register(client, "alice")
        alice_headers = _headers(alice["access_token"])
        created = client.post(
            "/api/workspaces", json={"name": "Redes de Alice"}, headers=alice_headers
        )
        assert created.status_code == 201, created.text
        workspace_id = created.json()["id"]

        bob = _register(client, "bob")
        bob_headers = _headers(bob["access_token"])
        assert client.get("/api/workspaces", headers=bob_headers).json() == []
        assert (
            client.get(f"/api/workspaces/{workspace_id}", headers=bob_headers).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/workspaces/{workspace_id}/materials", headers=bob_headers
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/workspaces/{workspace_id}/export?format=json", headers=bob_headers
            ).status_code
            == 404
        )

        uploaded = client.post(
            f"/api/workspaces/{workspace_id}/materials",
            headers=alice_headers,
            files={"files": ("apuntes.txt", b"contenido de alice", "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        material_id = uploaded.json()[0]["id"]
        assert (
            client.get(
                f"/api/workspaces/{workspace_id}/materials/{material_id}",
                headers=bob_headers,
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/workspaces/{workspace_id}/materials/{material_id}",
                headers=bob_headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/workspaces/{workspace_id}/materials/import",
                headers=bob_headers,
                json={"url": "http://127.0.0.1:9/no-debe-descargarse"},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/workspaces/{workspace_id}/materials/{material_id}",
                headers=alice_headers,
            ).status_code
            == 200
        )

        alice_list = client.get("/api/workspaces", headers=alice_headers).json()
        assert [item["id"] for item in alice_list] == [workspace_id]

        status = client.get("/api/auth/status", headers=bob_headers).json()
        assert status["auth_required"] is True
        assert status["authenticated"] is True
        assert status["user"]["username"] == "bob"


def test_login_logout_and_password_validation(tmp_path):
    app = create_app(settings=_auth_settings(tmp_path), provider=FakeLLMProvider())
    with TestClient(app) as client:
        _register(client, "carol")

        wrong = client.post(
            "/api/auth/login", json={"username": "carol", "password": "incorrecta"}
        )
        assert wrong.status_code == 401

        login = client.post(
            "/api/auth/login", json={"username": "carol", "password": "secreto123"}
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        assert client.get("/api/auth/me", headers=_headers(token)).json()["username"] == "carol"

        logout = client.post("/api/auth/logout", headers=_headers(token))
        assert logout.status_code == 204
        assert client.get("/api/auth/me", headers=_headers(token)).status_code == 401

        duplicate = client.post(
            "/api/auth/register",
            json={"username": "carol", "password": "secreto123"},
        )
        assert duplicate.status_code == 409
        short = client.post(
            "/api/auth/register",
            json={"username": "dave", "password": "corta"},
        )
        assert short.status_code == 422


def test_anonymous_data_is_adopted_by_first_real_user(tmp_path):
    app = create_app(settings=_auth_settings(tmp_path, required=False), provider=FakeLLMProvider())
    with TestClient(app) as client:
        created = client.post("/api/workspaces", json={"name": "Datos anónimos"})
        assert created.status_code == 201
        workspace_id = created.json()["id"]
        assert [item["id"] for item in client.get("/api/workspaces").json()] == [workspace_id]

        registered = _register(client, "erin")
        headers = _headers(registered["access_token"])
        owned = client.get("/api/workspaces", headers=headers).json()
        assert [item["id"] for item in owned] == [workspace_id]

        # El modo anónimo ya no ve los datos que pasaron al usuario real.
        assert client.get("/api/workspaces").json() == []
