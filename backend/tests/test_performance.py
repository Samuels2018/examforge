from sqlalchemy import event

from tests.helpers import create_workspace, upload_material


def _select_counter(engine):
    counter = {"selects": 0}

    def before_cursor_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            counter["selects"] += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    return counter, before_cursor_execute


def test_workspace_list_has_constant_query_count(app, client):
    engine = app.state.engine
    create_workspace(client, "Uno")
    counter, listener = _select_counter(engine)
    try:
        response = client.get("/api/workspaces")
        assert response.status_code == 200
        queries_with_one = counter["selects"]

        for index in range(2, 7):
            create_workspace(client, f"Evaluación {index}")
        counter["selects"] = 0
        response = client.get("/api/workspaces")
        assert response.status_code == 200
        queries_with_six = counter["selects"]
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert queries_with_one == queries_with_six
    assert queries_with_six <= 6


def test_materials_list_has_constant_query_count(app, client):
    workspace_id = create_workspace(client)
    for index in range(5):
        upload_material(client, workspace_id, filename=f"material-{index}.txt")

    engine = app.state.engine
    counter, listener = _select_counter(engine)
    try:
        response = client.get(f"/api/workspaces/{workspace_id}/materials")
        assert response.status_code == 200
        assert response.json()["total"] == 5
        selects = counter["selects"]
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert selects <= 3
