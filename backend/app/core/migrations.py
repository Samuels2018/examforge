import json
import logging

from sqlalchemy import Engine

from app.services.signatures import exercise_signature

logger = logging.getLogger(__name__)


def apply_lightweight_migrations(engine: Engine) -> None:
    """Migraciones mínimas para SQLite sin Alembic.

    `create_all` no añade columnas a tablas existentes. Esta función cubre los
    cambios aditivos de las fases 4 y 5 para no romper bases de datos ya creadas.
    """
    if not engine.url.drivername.startswith("sqlite"):
        return

    with engine.begin() as connection:
        workspace_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(workspaces)")
        }
        if "owner_id" not in workspace_columns:
            logger.info("Añadiendo columna workspaces.owner_id")
            connection.exec_driver_sql(
                "ALTER TABLE workspaces ADD COLUMN owner_id VARCHAR(32) "
                "REFERENCES users(id) ON DELETE SET NULL"
            )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_workspaces_owner_id ON workspaces(owner_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_workspaces_owner_updated "
            "ON workspaces(owner_id, updated_at)"
        )

        exercise_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(exercises)")
        }
        if "signature" not in exercise_columns:
            logger.info("Añadiendo columna exercises.signature")
            connection.exec_driver_sql(
                "ALTER TABLE exercises ADD COLUMN signature VARCHAR(64)"
            )

        # Backfill único: deduplicar sin cargar todos los ejercicios en memoria.
        rows = connection.exec_driver_sql(
            "SELECT id, question, options FROM exercises WHERE signature IS NULL"
        ).fetchall()
        for exercise_id, question, raw_options in rows:
            try:
                options = json.loads(raw_options) if raw_options else []
            except (TypeError, ValueError):
                options = []
            signature = exercise_signature(question or "", options if isinstance(options, list) else [])
            connection.exec_driver_sql(
                "UPDATE exercises SET signature = ? WHERE id = ?",
                (signature, exercise_id),
            )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_exercises_signature ON exercises(signature)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_exercises_workspace_signature "
            "ON exercises(workspace_id, signature)"
        )
