from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import FakeLLMProvider
from tests.helpers import create_workspace


def _settings(tmp_path, **overrides) -> Settings:
    values = {
        "environment": "test",
        "database_url": f"sqlite:///{tmp_path / 'security.db'}",
        "upload_dir": tmp_path / "uploads",
        "llm_provider": "offline",
        "embedding_provider": "offline",
    }
    values.update(overrides)
    return Settings(**values)


def test_rate_limit_returns_structured_429(tmp_path):
    settings = _settings(tmp_path, rate_limit_requests=3, rate_limit_window_seconds=60)
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/api/workspaces").status_code == 200
        response = client.get("/api/workspaces")
        assert response.status_code == 429
        assert response.headers["retry-after"]
        body = response.json()
        assert body["error"]["code"] == "rate_limited"
        assert body["error"]["details"]["retry_after_seconds"] >= 1

        health = client.get("/api/health")
        assert health.status_code == 200


def test_rate_limit_can_be_disabled(tmp_path):
    settings = _settings(tmp_path, rate_limit_enabled=False, rate_limit_requests=1)
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        for _ in range(4):
            assert client.get("/api/workspaces").status_code == 200


def test_upload_file_count_limit_is_configurable(tmp_path):
    settings = _settings(tmp_path, max_files_per_upload=1)
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        workspace_id = create_workspace(client)
        response = client.post(
            f"/api/workspaces/{workspace_id}/materials",
            files=[
                ("files", ("a.txt", b"contenido uno", "text/plain")),
                ("files", ("b.txt", b"contenido dos", "text/plain")),
            ],
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "too_many_files"


def test_audit_records_mutations_but_not_reads(client):
    workspace_id = create_workspace(client, name="Auditoría")

    response = client.get("/api/audit")
    assert response.status_code == 200
    events = response.json()
    assert events
    assert any(
        event["method"] == "POST"
        and event["path"] == "/api/workspaces"
        and event["status_code"] == 201
        for event in events
    )
    assert all(event["method"] != "GET" for event in events)

    before = len(events)
    client.get("/api/workspaces")
    after = client.get("/api/audit").json()
    assert len(after) == before

    client.delete(f"/api/workspaces/{workspace_id}")
    deleted = client.get("/api/audit").json()
    assert any(event["method"] == "DELETE" for event in deleted)


def test_audit_can_be_disabled(tmp_path):
    settings = _settings(tmp_path, audit_enabled=False)
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        create_workspace(client)
        assert client.get("/api/audit").json() == []
