import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.celery_app import celery_app
from app.config import settings

BACKUP_DIR = os.environ.get("BACKUP_DIR", "/opt/clipbandit/backups")
BACKUP_RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "14"))


def _database_parts() -> tuple[str, str, str, str, str]:
    parsed = urlparse(settings.database_sync_url)
    db_host = os.environ.get("DB_HOST") or parsed.hostname or "postgres"
    db_port = os.environ.get("DB_PORT") or str(parsed.port or 5432)
    db_user = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER") or parsed.username or settings.postgres_user
    db_name = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB") or parsed.path.lstrip("/") or settings.postgres_db
    db_password = (
        os.environ.get("DB_PASSWORD")
        or os.environ.get("POSTGRES_PASSWORD")
        or parsed.password
        or settings.postgres_password
    )
    return db_host, db_port, db_user, db_name, db_password


@celery_app.task(name="tasks.backup_database")
def backup_database() -> str:
    """
    Dumps PostgreSQL to a gzipped SQL file and rotates old local backups.

    Known limitation: backups currently land on the same VPS disk as the DB.
    This protects against accidental data deletion and software errors, but not
    full VPS or disk failure. Once B2 backup storage is wired, upload the .sql.gz
    after creation and verify object size before relying on off-box backups.
    """
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = backup_dir / f"postbandit_{timestamp}.sql.gz"

    db_host, db_port, db_user, db_name, db_password = _database_parts()
    if not all([db_host, db_port, db_user, db_name, db_password]):
        raise RuntimeError(
            "backup_database: missing one or more database connection values "
            "for host, port, user, name, or password"
        )

    dump_cmd = [
        "bash",
        "-lc",
        "pg_dump -h \"$DB_HOST\" -p \"$DB_PORT\" -U \"$DB_USER\" -d \"$DB_NAME\" --no-password | gzip > \"$OUTPUT_PATH\"",
    ]
    env = {
        **os.environ,
        "PGPASSWORD": db_password,
        "DB_HOST": db_host,
        "DB_PORT": db_port,
        "DB_USER": db_user,
        "DB_NAME": db_name,
        "OUTPUT_PATH": str(output_path),
    }
    result = subprocess.run(dump_cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"backup_database: pg_dump failed (exit {result.returncode})\n"
            f"stderr: {result.stderr[-500:]}"
        )

    file_size = output_path.stat().st_size
    if file_size <= 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("backup_database: created backup is empty")

    file_size_mb = file_size / (1024 * 1024)
    print(f"[backup_database] Created {output_path} ({file_size_mb:.1f} MB)")

    cutoff = datetime.now(timezone.utc) - timedelta(days=BACKUP_RETENTION_DAYS)
    removed = 0
    for backup_file in backup_dir.iterdir():
        if not backup_file.name.startswith("postbandit_") or not backup_file.name.endswith(".sql.gz"):
            continue
        if backup_file.stat().st_mtime < cutoff.timestamp():
            backup_file.unlink()
            removed += 1

    if removed:
        print(f"[backup_database] Rotated {removed} backup(s) older than {BACKUP_RETENTION_DAYS} days")

    return str(output_path)
