"""Esquema inicial completo.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-08
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.core.db import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Línea base del esquema actual. `checkfirst=True` permite aplicar Alembic
    # sobre una base de datos ya creada por `Base.metadata.create_all`.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
