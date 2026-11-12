from app.services.embeddings.offline import OfflineEmbeddingProvider
from app.services.embeddings.retrieval import _cosine
from tests.helpers import create_workspace, generate_exercises, upload_material


def test_offline_embeddings_are_deterministic_and_rank_related_text():
    provider = OfflineEmbeddingProvider(dimensions=192)
    first = provider.embed(["El índice B-tree acelera las consultas de rango."])
    second = provider.embed(["El índice B-tree acelera las consultas de rango."])
    query = provider.embed(["índice para consultas"]).vectors[0]
    related = provider.embed(["Los índices B-tree y hash optimizan búsquedas."]).vectors[0]
    unrelated = provider.embed(["La fotosíntesis transforma la luz en energía."]).vectors[0]

    assert first.vectors == second.vectors
    assert len(first.vectors[0]) == 192
    assert _cosine(query, related) > _cosine(query, unrelated)


def test_mastery_diagnostics_and_plan(client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    exercises = generate_exercises(client, workspace_id)["exercises"]
    exercise_id = exercises[0]["id"]

    for answer in ("b", "c"):
        response = client.post(
            f"/api/workspaces/{workspace_id}/exercises/{exercise_id}/attempts",
            json={"answer": answer},
        )
        assert response.status_code == 201
        assert response.json()["is_correct"] is False

    mastery = client.get(f"/api/workspaces/{workspace_id}/mastery")
    assert mastery.status_code == 200
    body = mastery.json()
    assert body["topics"][0]["topic"] == "TCP"
    assert body["topics"][0]["attempts"] == 2
    assert body["topics"][0]["correct"] == 0
    assert body["topics"][0]["mastery"] == 0.0

    diagnostics = client.get(f"/api/workspaces/{workspace_id}/diagnostics")
    assert diagnostics.status_code == 200
    patterns = diagnostics.json()
    assert patterns[0]["topic"] == "TCP"
    assert patterns[0]["error_type"] == "seleccion_incorrecta"
    assert patterns[0]["count"] == 2

    progress = client.get(f"/api/workspaces/{workspace_id}/progress")
    assert progress.status_code == 200
    assert progress.json()["error_patterns"][0]["count"] == 2
    assert progress.json()["mastery"][0]["topic"] == "TCP"

    plan = client.get(f"/api/workspaces/{workspace_id}/study-plan")
    assert plan.status_code == 200
    assert any("Rompe el patrón" in step["title"] for step in plan.json()["steps"])

    correct = client.post(
        f"/api/workspaces/{workspace_id}/exercises/{exercise_id}/attempts",
        json={"answer": "a"},
    )
    assert correct.status_code == 201
    mastery_after = client.get(f"/api/workspaces/{workspace_id}/mastery").json()
    assert mastery_after["topics"][0]["attempts"] == 3
    assert mastery_after["topics"][0]["correct"] == 1
    assert mastery_after["topics"][0]["mastery"] > 0


def test_guided_explanation_and_variation(client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    exercises = generate_exercises(client, workspace_id)["exercises"]
    exercise_id = exercises[0]["id"]

    first = client.get(f"/api/workspaces/{workspace_id}/exercises/{exercise_id}/guide")
    assert first.status_code == 200
    guide = first.json()
    assert guide["exercise_id"] == exercise_id
    assert guide["provider"] == "deterministic"
    assert len(guide["steps"]) == 4
    assert "Explicación" in guide["concept"]

    second = client.get(f"/api/workspaces/{workspace_id}/exercises/{exercise_id}/guide")
    assert second.status_code == 200
    assert second.json()["created_at"] == guide["created_at"]

    variation = client.post(
        f"/api/workspaces/{workspace_id}/exercises/{exercise_id}/variation"
    )
    assert variation.status_code == 201, variation.text
    body = variation.json()
    assert body["created"] == 1
    assert body["exercises"][0]["id"] != exercise_id
    assert body["exercises"][0]["topic"] == "TCP"


def test_timed_exam_flow_updates_progress_and_is_idempotent(client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    generate_exercises(client, workspace_id)

    started = client.post(
        f"/api/workspaces/{workspace_id}/exams",
        json={"count": 3, "time_limit_minutes": 15},
    )
    assert started.status_code == 201, started.text
    exam = started.json()
    assert exam["status"] == "active"
    assert exam["seconds_remaining"] > 0
    assert exam["total_questions"] == 3
    assert all("correct_answer" not in question for question in exam["questions"])

    answers = []
    for question in exam["questions"]:
        if question["kind"] == "multiple_choice":
            answer = "a"
        elif question["kind"] == "true_false":
            answer = "true"
        else:
            answer = "respuesta correcta"
        answers.append({"item_id": question["id"], "answer": answer})

    submitted = client.post(
        f"/api/workspaces/{workspace_id}/exams/{exam['id']}/submit",
        json={"answers": answers, "duration_seconds": 90},
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["correct_count"] == 3
    assert result["score"] >= 0.9
    assert result["duration_seconds"] == 90
    assert all(item["is_correct"] for item in result["items"])

    progress = client.get(f"/api/workspaces/{workspace_id}/progress").json()
    assert progress["total_attempts"] == 3

    again = client.post(
        f"/api/workspaces/{workspace_id}/exams/{exam['id']}/submit",
        json={"answers": [], "duration_seconds": 1},
    )
    assert again.status_code == 200
    assert again.json()["correct_count"] == 3
    assert client.get(f"/api/workspaces/{workspace_id}/attempts").json()["total"] == 3


def test_exam_requires_enough_exercises(client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    generate_exercises(client, workspace_id, count=2)

    response = client.post(
        f"/api/workspaces/{workspace_id}/exams",
        json={"count": 10},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_material"
