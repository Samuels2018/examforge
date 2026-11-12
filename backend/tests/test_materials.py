from tests.helpers import MATERIAL_TEXT, create_workspace, upload_material


def test_upload_material_parses_and_chunks(client):
    workspace_id = create_workspace(client)
    material = upload_material(client, workspace_id)

    assert material["status"] == "ready"
    assert material["char_count"] > 300
    assert material["chunk_count"] >= 1
    assert material["error_message"] is None

    listed = client.get(f"/api/workspaces/{workspace_id}/materials")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == material["id"]

    detail = client.get(f"/api/workspaces/{workspace_id}/materials/{material['id']}")
    assert detail.status_code == 200
    assert detail.json()["preview"].startswith("El modelo TCP/IP")
    assert detail.json()["chunk_count"] == material["chunk_count"]

    workspace_detail = client.get("/api/workspaces").json()[0]
    assert workspace_detail["material_count"] == 1


def test_upload_multiple_files_and_delete(client):
    workspace_id = create_workspace(client)
    response = client.post(
        f"/api/workspaces/{workspace_id}/materials",
        files=[
            ("files", ("uno.txt", MATERIAL_TEXT.encode(), "text/plain")),
            ("files", ("dos.md", ("# Tema\n\n" + MATERIAL_TEXT).encode(), "text/markdown")),
        ],
    )
    assert response.status_code == 201
    materials = response.json()
    assert len(materials) == 2
    assert all(item["status"] == "ready" for item in materials)

    deleted = client.delete(
        f"/api/workspaces/{workspace_id}/materials/{materials[0]['id']}"
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/workspaces/{workspace_id}/materials").json()["total"] == 1


def test_unsupported_file_is_rejected(client):
    workspace_id = create_workspace(client)
    response = client.post(
        f"/api/workspaces/{workspace_id}/materials",
        files=[("files", ("virus.exe", b"MZ...", "application/octet-stream"))],
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file"


def test_empty_file_is_rejected(client):
    workspace_id = create_workspace(client)
    response = client.post(
        f"/api/workspaces/{workspace_id}/materials",
        files=[("files", ("vacio.txt", b"", "text/plain"))],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_material"


def test_materials_unknown_workspace(client):
    response = client.get("/api/workspaces/no-existe/materials")
    assert response.status_code == 404
