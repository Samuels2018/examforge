from tests.helpers import create_workspace, generate_exercises, upload_material


def test_export_markdown_json_and_pdf(app, client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    generate_exercises(client, workspace_id, count=2)

    markdown = client.get(f"/api/workspaces/{workspace_id}/export?format=markdown")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in markdown.headers["content-disposition"]
    body = markdown.text
    assert "# Examen de redes" in body
    assert "## Materiales" in body
    assert "redes.txt" in body
    assert "## Plan de ataque" in body
    assert "## Ejercicios" in body
    assert "**Respuesta:**" in body

    exported_json = client.get(f"/api/workspaces/{workspace_id}/export?format=json")
    assert exported_json.status_code == 200
    payload = exported_json.json()
    assert payload["workspace"]["id"] == workspace_id
    assert payload["summary"]["materials"] == 1
    assert payload["summary"]["exercises"] == 2
    assert len(payload["materials"]) == 1
    assert len(payload["exercises"]) == 2
    assert "study_plan" in payload
    assert payload["study_plan"]["steps"]

    pdf = client.get(f"/api/workspaces/{workspace_id}/export?format=pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-1.4")
    assert pdf.content.rstrip().endswith(b"%%EOF")
    assert len(pdf.content) > 500


def test_export_rejects_unknown_format(app, client):
    workspace_id = create_workspace(client)
    response = client.get(f"/api/workspaces/{workspace_id}/export?format=docx")
    assert response.status_code == 422
