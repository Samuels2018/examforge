import sqlite3

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import FakeLLMProvider


def test_lightweight_migration_adds_owner_id_to_existing_sqlite(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE workspaces (
                id VARCHAR(32) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT NOT NULL,
                exam_date DATE,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?)",
            ("legacy", "Evaluación antigua", "", None, "2026-01-01", "2026-01-01"),
        )

    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{database}",
        upload_dir=tmp_path / "uploads",
        llm_provider="offline",
        embedding_provider="offline",
    )
    app = create_app(settings=settings, provider=FakeLLMProvider())

    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(workspaces)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(workspaces)")}
    assert "owner_id" in columns
    assert "ix_workspaces_owner_id" in indexes
    assert "ix_workspaces_owner_updated" in indexes

    with TestClient(app) as client:
        response = client.get("/api/workspaces")
        assert response.status_code == 200
        assert response.json()[0]["id"] == "legacy"
