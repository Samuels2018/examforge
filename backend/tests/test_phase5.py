import io
import time

import polars as pl
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import Exercise
from tests.conftest import FakeLLMProvider
from tests.helpers import create_workspace, generate_exercises, upload_material


def _wait_for_material(client: TestClient, workspace_id: str, material_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/workspaces/{workspace_id}/materials")
        assert response.status_code == 200
        material = next(
            item for item in response.json()["items"] if item["id"] == material_id
        )
        if material["status"] != "processing":
            return material
        time.sleep(0.05)
    raise AssertionError("El material no terminó de procesarse a tiempo")


def test_large_upload_is_processed_in_background(tmp_path):
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'background.db'}",
        upload_dir=tmp_path / "uploads",
        llm_provider="offline",
        embedding_provider="offline",
        background_processing_threshold_mb=0,
        background_workers=1,
    )
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        workspace_id = create_workspace(client)
        material = upload_material(client, workspace_id)
        assert material["status"] == "processing"

        ready = _wait_for_material(client, workspace_id, material["id"])
        assert ready["status"] == "ready"
        assert ready["chunk_count"] > 0
        assert ready["char_count"] > 0


def test_csv_and_parquet_include_column_profiles(client):
    workspace_id = create_workspace(client)
    csv_data = b"name,score,team\nAna,9,A\nLuis,7,B\nMarta,10,A\n"
    response = client.post(
        f"/api/workspaces/{workspace_id}/materials",
        files=[("files", ("notas.csv", csv_data, "text/csv"))],
    )
    assert response.status_code == 201, response.text
    csv_material = response.json()[0]
    detail = client.get(
        f"/api/workspaces/{workspace_id}/materials/{csv_material['id']}"
    ).json()
    assert "Tipo: CSV" in detail["preview"]
    assert "Filas: 3" in detail["preview"]
    assert "Perfil de columnas" in detail["preview"]
    assert "media=8.667" in detail["preview"]

    buffer = io.BytesIO()
    pl.DataFrame(
        {
            "ciudad": ["Madrid", "Lima", "Bogotá"],
            "temperatura": [21.5, 19.0, 17.5],
        }
    ).write_parquet(buffer)
    response = client.post(
        f"/api/workspaces/{workspace_id}/materials",
        files=[("files", ("clima.parquet", buffer.getvalue(), "application/octet-stream"))],
    )
    assert response.status_code == 201, response.text
    parquet_material = response.json()[0]
    detail = client.get(
        f"/api/workspaces/{workspace_id}/materials/{parquet_material['id']}"
    ).json()
    assert "Tipo: Parquet" in detail["preview"]
    assert "Filas: 3" in detail["preview"]
    assert "temperatura" in detail["preview"]


def test_workspace_material_quota_is_enforced(client, app):
    app.state.settings.workspace_max_materials = 1
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)

    response = client.post(
        f"/api/workspaces/{workspace_id}/materials",
        files=[("files", ("extra.txt", b"contenido adicional", "text/plain"))],
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quota_exceeded"


def test_attempt_history_supports_keyset_cursor(client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    exercises = generate_exercises(client, workspace_id, count=3)["exercises"]

    for exercise in exercises:
        response = client.post(
            f"/api/workspaces/{workspace_id}/exercises/{exercise['id']}/attempts",
            json={"answer": "a"},
        )
        assert response.status_code == 201, response.text

    first = client.get(f"/api/workspaces/{workspace_id}/attempts?limit=2")
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["total"] == 3
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"]

    second = client.get(
        f"/api/workspaces/{workspace_id}/attempts?limit=2&cursor={first_body['next_cursor']}"
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None
    first_ids = {item["id"] for item in first_body["items"]}
    second_ids = {item["id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert len(first_ids | second_ids) == 3


def test_generation_cache_and_metrics(client, app, provider):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    payload = {"count": 2, "difficulties": ["basic"], "focus": "TCP"}

    first = client.post(
        f"/api/workspaces/{workspace_id}/exercises/generate", json=payload
    )
    assert first.status_code == 201, first.text
    assert first.json()["cached"] is False
    assert first.json()["usage"]["total_tokens"] > 0

    second = client.post(
        f"/api/workspaces/{workspace_id}/exercises/generate", json=payload
    )
    assert second.status_code == 201, second.text
    assert second.json()["cached"] is True
    assert second.json()["created"] == first.json()["created"]
    assert len(provider.calls) == 1

    metrics = client.get(f"/api/workspaces/{workspace_id}/generation-metrics")
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["total_generations"] == 2
    assert body["cached_generations"] == 1
    assert body["cache_hit_rate"] == 0.5
    assert body["average_duration_ms"] >= 0
    assert len(body["recent"]) == 2

    with app.state.session_factory() as session:
        signatures = session.query(Exercise.signature).all()
        assert signatures and all(signature for (signature,) in signatures)
