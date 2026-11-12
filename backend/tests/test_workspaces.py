def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "fake"


def test_workspace_crud(client):
    created = client.post(
        "/api/workspaces",
        json={"name": "  Cálculo II  ", "description": "Integrales", "exam_date": "2026-12-01"},
    )
    assert created.status_code == 201
    workspace = created.json()
    assert workspace["name"] == "Cálculo II"
    assert workspace["exam_date"] == "2026-12-01"
    workspace_id = workspace["id"]

    listed = client.get("/api/workspaces")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [workspace_id]
    assert listed.json()[0]["material_count"] == 0

    fetched = client.get(f"/api/workspaces/{workspace_id}")
    assert fetched.status_code == 200
    assert fetched.json()["description"] == "Integrales"

    patched = client.patch(
        f"/api/workspaces/{workspace_id}",
        json={"description": "Integrales impropias"},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Integrales impropias"

    deleted = client.delete(f"/api/workspaces/{workspace_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/workspaces/{workspace_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_workspace_validation(client):
    response = client.post("/api/workspaces", json={"name": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_two_workspaces_are_independent(client):
    first = client.post("/api/workspaces", json={"name": "Álgebra"}).json()["id"]
    second = client.post("/api/workspaces", json={"name": "Historia"}).json()["id"]
    listed = client.get("/api/workspaces").json()
    assert {item["id"] for item in listed} == {first, second}
    assert len({item["name"] for item in listed}) == 2
