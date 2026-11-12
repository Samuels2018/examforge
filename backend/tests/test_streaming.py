import json
import threading

import pytest

from app.core.errors import GenerationCancelledError
from app.models import Exercise
from app.schemas.exercise import GenerateRequest
from app.services.generation import GenerationService
from app.services.generation_registry import GenerationRegistry
from tests.helpers import create_workspace, upload_material


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if line]
        if not lines:
            continue
        name_line = next(
            (line for line in lines if line.startswith("event: ")), None
        )
        data_line = next(
            (line for line in lines if line.startswith("data: ")), None
        )
        if name_line is None or data_line is None:
            continue
        events.append(
            (
                name_line.removeprefix("event: "),
                json.loads(data_line.removeprefix("data: ")),
            )
        )
    return events


def test_generation_streams_progress_and_result(client, app):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)

    with client.stream(
        "POST",
        f"/api/workspaces/{workspace_id}/exercises/generate/stream",
        json={"count": 2, "difficulties": ["basic"], "focus": "TCP"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-generation-id"]
        body = "".join(response.iter_text())

    events = _sse_events(body)
    names = [name for name, _ in events]
    assert names[0] == "start"
    assert "progress" in names
    assert names[-1] == "result"
    result = events[-1][1]
    assert result["created"] == 2
    assert len(result["exercises"]) == 2

    with app.state.session_factory() as session:
        assert session.query(Exercise).filter_by(workspace_id=workspace_id).count() == 2


def test_cancel_endpoint_marks_generation(client, app):
    workspace_id = create_workspace(client)
    registry = GenerationRegistry()
    app.state.generation_registry = registry
    handle = registry.create(workspace_id)

    response = client.post(
        f"/api/workspaces/{workspace_id}/exercises/generate/{handle.id}/cancel"
    )
    assert response.status_code == 204
    assert handle.cancel_event.is_set()

    unknown = client.post(
        f"/api/workspaces/{workspace_id}/exercises/generate/no-existe/cancel"
    )
    assert unknown.status_code == 404


def test_generation_service_aborts_before_commit_when_cancelled(client, app, provider):
    workspace_id = create_workspace(client)
    upload_material(client, workspace_id)
    cancel_event = threading.Event()
    cancel_event.set()

    with app.state.session_factory() as session:
        session.info["owner_id"] = None
        service = GenerationService(session, app.state.settings, provider)
        with pytest.raises(GenerationCancelledError):
            service.generate(
                workspace_id,
                GenerateRequest(count=2, difficulties=["basic"], focus="TCP"),
                cancel_event=cancel_event,
            )
        assert session.query(Exercise).filter_by(workspace_id=workspace_id).count() == 0
