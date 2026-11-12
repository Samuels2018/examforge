import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import FakeLLMProvider
from tests.helpers import create_workspace


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'backup.db'}",
        upload_dir=tmp_path / "uploads",
        backup_dir=tmp_path / "backups",
        llm_provider="offline",
        embedding_provider="offline",
    )


def test_sqlite_backup_and_restore(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        first = create_workspace(client, name="Antes del backup")
        assert first
        created = client.post("/api/maintenance/backup")
        assert created.status_code == 201, created.text
        filename = created.json()["filename"]
        assert created.json()["size_bytes"] > 0

        second = create_workspace(client, name="Después del backup")

        listed = client.get("/api/maintenance/backups")
        assert listed.status_code == 200
        assert any(item["filename"] == filename for item in listed.json())

        restored = client.post("/api/maintenance/restore", json={"filename": filename})
        assert restored.status_code == 200, restored.text

        workspaces = client.get("/api/workspaces").json()
        names = {workspace["name"] for workspace in workspaces}
        assert "Antes del backup" in names
        assert "Después del backup" not in names
        assert second not in {workspace["id"] for workspace in workspaces}


def test_restore_rejects_invalid_names(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        response = client.post("/api/maintenance/restore", json={"filename": "../secret.db"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "app_error"


def test_backup_list_is_empty_before_first_backup(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings=settings, provider=FakeLLMProvider())
    with TestClient(app) as client:
        assert client.get("/api/maintenance/backups").json() == []


def test_alembic_upgrade_creates_full_schema(tmp_path, monkeypatch):
    database = tmp_path / "alembic.db"
    monkeypatch.setenv("EXAMFORGE_DATABASE_URL", f"sqlite:///{database}")
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))

    command.upgrade(config, "head")

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"workspaces", "materials", "exercises", "attempts", "audit_logs"} <= tables
    assert "alembic_version" in tables
