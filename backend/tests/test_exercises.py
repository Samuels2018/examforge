from tests.helpers import create_workspace, generate_exercises, upload_material


def test_generate_requires_material(client):
    workspace_id = create_workspace(client)
    response = client.post(
        f"/api/workspaces/{workspace_id}/exercises/generate",
        json={"count": 3},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_material"


def test_generate_unknown_workspace(client):
    response = client.post(
        "/api/workspaces/no-existe/exercises/generate",
        json={"count": 3},
    )
    assert response.status_code == 404


def test_generate_lists_and_hides_answers(client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    result = generate_exercises(client, workspace_id)

    assert result["provider"] == "fake"
    assert result["requested"] == 6
    assert result["created"] == 6
    assert len(result["exercises"]) == 6
    for exercise in result["exercises"]:
        assert "correct_answer" not in exercise
        assert "explanation" not in exercise

    listed = client.get(f"/api/workspaces/{workspace_id}/exercises")
    assert listed.status_code == 200
    assert listed.json()["total"] == 6

    basics = client.get(
        f"/api/workspaces/{workspace_id}/exercises", params={"difficulty": "basic"}
    )
    assert basics.json()["total"] == 2

    exercise_id = result["exercises"][0]["id"]
    detail = client.get(f"/api/workspaces/{workspace_id}/exercises/{exercise_id}")
    assert detail.status_code == 200
    assert "correct_answer" not in detail.json()

    missing = client.get(f"/api/workspaces/{workspace_id}/exercises/no-existe")
    assert missing.status_code == 404


def test_attempts_feedback_progress_and_plan(client):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    result = generate_exercises(client, workspace_id)
    exercises = result["exercises"]
    multiple_choice_id = exercises[0]["id"]
    short_answer = next(item for item in exercises if item["kind"] == "short_answer")

    wrong = client.post(
        f"/api/workspaces/{workspace_id}/exercises/{multiple_choice_id}/attempts",
        json={"answer": "b", "duration_seconds": 12},
    )
    assert wrong.status_code == 201
    wrong_body = wrong.json()
    assert wrong_body["is_correct"] is False
    assert wrong_body["score"] == 0.0
    assert wrong_body["correct_answer"] == "a: Opción correcta"
    assert "Explicación 1" in wrong_body["explanation"]

    right = client.post(
        f"/api/workspaces/{workspace_id}/exercises/{multiple_choice_id}/attempts",
        json={"answer": "a"},
    )
    assert right.status_code == 201
    assert right.json()["is_correct"] is True
    assert right.json()["score"] == 1.0

    short_correct = client.post(
        f"/api/workspaces/{workspace_id}/exercises/{short_answer['id']}/attempts",
        json={"answer": "es una respuesta correcta"},
    )
    assert short_correct.status_code == 201
    assert short_correct.json()["provider"] == "fake"
    assert short_correct.json()["is_correct"] is True

    short_wrong = client.post(
        f"/api/workspaces/{workspace_id}/exercises/{short_answer['id']}/attempts",
        json={"answer": "no lo sé"},
    )
    assert short_wrong.status_code == 201
    assert short_wrong.json()["is_correct"] is False

    history = client.get(f"/api/workspaces/{workspace_id}/attempts")
    assert history.status_code == 200
    assert history.json()["total"] == 4
    assert history.json()["items"][0]["is_correct"] is False

    progress = client.get(f"/api/workspaces/{workspace_id}/progress")
    assert progress.status_code == 200
    body = progress.json()
    assert body["total_exercises"] == 6
    assert body["attempted_exercises"] == 2
    assert body["total_attempts"] == 4
    assert body["correct_attempts"] == 2
    assert body["accuracy"] == 0.5
    assert body["weak_topics"][0]["topic"] == "TCP"
    assert len(body["recent_attempts"]) == 4

    plan = client.get(f"/api/workspaces/{workspace_id}/study-plan")
    assert plan.status_code == 200
    plan_body = plan.json()
    assert "TCP" in plan_body["summary"]
    assert plan_body["steps"]
    assert any(step["focus_topic"] == "TCP" for step in plan_body["steps"])


def test_attempt_unknown_exercise(client):
    workspace_id = create_workspace(client)
    response = client.post(
        f"/api/workspaces/{workspace_id}/exercises/no-existe/attempts",
        json={"answer": "a"},
    )
    assert response.status_code == 404
