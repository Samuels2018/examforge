from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import FakeLLMProvider

EXPECTED_ENDPOINTS = {
    ("get", "/api/health"),
    ("get", "/api/auth/status"),
    ("post", "/api/auth/register"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/logout"),
    ("get", "/api/auth/me"),
    ("get", "/api/audit"),
    ("get", "/api/workspaces"),
    ("post", "/api/workspaces"),
    ("get", "/api/workspaces/{workspace_id}"),
    ("patch", "/api/workspaces/{workspace_id}"),
    ("delete", "/api/workspaces/{workspace_id}"),
    ("get", "/api/workspaces/{workspace_id}/materials"),
    ("post", "/api/workspaces/{workspace_id}/materials"),
    ("post", "/api/workspaces/{workspace_id}/materials/import"),
    ("get", "/api/workspaces/{workspace_id}/materials/{material_id}"),
    ("delete", "/api/workspaces/{workspace_id}/materials/{material_id}"),
    ("post", "/api/workspaces/{workspace_id}/exercises/generate"),
    ("post", "/api/workspaces/{workspace_id}/exercises/generate/stream"),
    ("post", "/api/workspaces/{workspace_id}/exercises/generate/{generation_id}/cancel"),
    ("get", "/api/workspaces/{workspace_id}/exercises"),
    ("get", "/api/workspaces/{workspace_id}/exercises/{exercise_id}"),
    ("get", "/api/workspaces/{workspace_id}/exercises/{exercise_id}/guide"),
    ("post", "/api/workspaces/{workspace_id}/exercises/{exercise_id}/attempts"),
    ("get", "/api/workspaces/{workspace_id}/attempts"),
    ("get", "/api/workspaces/{workspace_id}/progress"),
    ("get", "/api/workspaces/{workspace_id}/study-plan"),
    ("get", "/api/workspaces/{workspace_id}/export"),
    ("get", "/api/workspaces/{workspace_id}/mastery"),
    ("get", "/api/workspaces/{workspace_id}/diagnostics"),
    ("get", "/api/workspaces/{workspace_id}/generation-metrics"),
    ("post", "/api/workspaces/{workspace_id}/exams"),
    ("get", "/api/workspaces/{workspace_id}/exams/{exam_id}"),
    ("post", "/api/workspaces/{workspace_id}/exams/{exam_id}/submit"),
    ("get", "/api/maintenance/backups"),
    ("post", "/api/maintenance/backup"),
    ("post", "/api/maintenance/restore"),
}


def test_openapi_exposes_the_documented_contract(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "ExamForge"
    paths = spec["paths"]
    for method, path in EXPECTED_ENDPOINTS:
        assert path in paths, f"Falta la ruta {path}"
        assert method in paths[path], f"Falta {method.upper()} {path}"

    for path, operations in paths.items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert operation.get("tags"), f"{method.upper()} {path} sin tag"
            assert operation.get("operationId"), f"{method.upper()} {path} sin operationId"


def test_health_contract(client):
    body = client.get("/api/health").json()
    assert set(body) == {
        "status",
        "app",
        "environment",
        "llm_mode",
        "llm_provider",
        "model",
        "background_queue_depth",
    }
    assert body["status"] == "ok"
    assert body["environment"] == "test"


def test_not_found_error_envelope(client):
    response = client.get("/api/workspaces/no-existe")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)
    assert "details" in body["error"]


def test_validation_error_envelope(client):
    response = client.post("/api/workspaces", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)


def test_unauthorized_error_envelope_when_auth_required(tmp_path):
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'contract.db'}",
        upload_dir=tmp_path / "uploads",
        backup_dir=tmp_path / "backups",
        auth_required=True,
        llm_provider="offline",
        embedding_provider="offline",
    )
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        response = client.get("/api/workspaces")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


def test_documented_crud_flow_shapes(client):
    create = client.post("/api/workspaces", json={"name": "Contrato"})
    assert create.status_code == 201
    workspace = create.json()
    assert {"id", "name", "description", "exam_date", "created_at", "updated_at"} <= set(
        workspace
    )

    detail = client.get(f"/api/workspaces/{workspace['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == workspace["id"]

    listing = client.get("/api/workspaces")
    assert listing.status_code == 200
    assert isinstance(listing.json(), list)
    assert listing.json()[0]["id"] == workspace["id"]
