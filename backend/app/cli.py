"""Utilidades de mantenimiento ejecutables sin levantar la API.

Uso:
    python -m app.cli backup
    python -m app.cli backups
    python -m app.cli restore examforge-20260101T120000000000Z.db
"""

import argparse
import sys

from app.core.config import Settings
from app.services.backup import BackupService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="examforge", description="Mantenimiento local")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("backup", help="Crea una copia de seguridad de SQLite")
    subcommands.add_parser("backups", help="Lista las copias disponibles")
    restore = subcommands.add_parser("restore", help="Restaura una copia de seguridad")
    restore.add_argument("filename")

    args = parser.parse_args(argv)
    service = BackupService(Settings())

    if args.command == "backup":
        info = service.create()
        print(f"Backup creado: {info.filename} ({info.size_bytes} bytes)")
        return 0
    if args.command == "backups":
        items = service.list()
        if not items:
            print("No hay copias de seguridad.")
            return 0
        for item in items:
            print(f"{item.filename}\t{item.size_bytes} bytes\t{item.created_at.isoformat()}")
        return 0
    if args.command == "restore":
        info = service.restore(args.filename)
        print(f"Base de datos restaurada desde {info.filename}. Reinicia la API si está activa.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
