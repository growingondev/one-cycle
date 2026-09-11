from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql


PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.app.core.config import settings


EVALUATION_DB_NAME = "one_cycle_evaluation_tmp"


def connect(database: str, *, autocommit: bool = False):
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=database,
        user=settings.postgres_user,
        password=settings.postgres_password,
        autocommit=autocommit,
    )


def create_database() -> None:
    with connect("postgres", autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (EVALUATION_DB_NAME,),
            )

            if cur.fetchone() is not None:
                raise RuntimeError(
                    f"평가 DB가 이미 존재합니다: {EVALUATION_DB_NAME}"
                )

            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(EVALUATION_DB_NAME)
                )
            )

    print(f"[OK] database created: {EVALUATION_DB_NAME}")


def enable_vector() -> None:
    with connect(EVALUATION_DB_NAME, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE EXTENSION IF NOT EXISTS vector"
            )

    print("[OK] pgvector enabled")


def run_migrations() -> None:
    env = os.environ.copy()
    env["POSTGRES_DB"] = EVALUATION_DB_NAME

    current_pythonpath = env.get("PYTHONPATH", "").strip()

    if current_pythonpath:
        env["PYTHONPATH"] = (
            str(PROJECT_ROOT)
            + os.pathsep
            + current_pythonpath
        )
    else:
        env["PYTHONPATH"] = str(PROJECT_ROOT)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "head",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        check=True,
    )

    print("[OK] alembic upgrade head")


def verify() -> None:
    with connect(EVALUATION_DB_NAME) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT extname
                FROM pg_extension
                WHERE extname = 'vector'
                """
            )
            vector = cur.fetchone()

            cur.execute(
                """
                SELECT version_num
                FROM alembic_version
                ORDER BY version_num
                """
            )
            migrations = cur.fetchall()

    if vector is None:
        raise RuntimeError("pgvector 확장이 활성화되지 않았습니다.")

    if not migrations:
        raise RuntimeError("Alembic migration 정보가 없습니다.")

    print(f"[OK] extension: {vector[0]}")
    print(
        "[OK] alembic version: "
        + ", ".join(row[0] for row in migrations)
    )


def main() -> None:
    create_database()
    enable_vector()
    run_migrations()
    verify()

    print(
        f"\n[READY] evaluation database: "
        f"{EVALUATION_DB_NAME}"
    )


if __name__ == "__main__":
    main()
