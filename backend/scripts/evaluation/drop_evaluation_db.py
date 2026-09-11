from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg import sql


PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.app.core.config import settings


EVALUATION_DB_NAME = "one_cycle_evaluation_tmp"
PRODUCTION_DB_NAME = "one_cycle"


def connect_admin():
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname="postgres",
        user=settings.postgres_user,
        password=settings.postgres_password,
        autocommit=True,
    )


def drop_evaluation_database() -> None:
    if EVALUATION_DB_NAME == PRODUCTION_DB_NAME:
        raise RuntimeError(
            "안전장치 오류: 평가 DB와 운영 DB 이름이 같습니다."
        )

    if EVALUATION_DB_NAME != "one_cycle_evaluation_tmp":
        raise RuntimeError(
            "허용되지 않은 DB 삭제 대상입니다: "
            f"{EVALUATION_DB_NAME}"
        )

    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM pg_database
                WHERE datname = %s
                """,
                (EVALUATION_DB_NAME,),
            )

            if cur.fetchone() is None:
                print(
                    "[SKIP] evaluation database does not exist: "
                    f"{EVALUATION_DB_NAME}"
                )
                return

            cur.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid()
                """,
                (EVALUATION_DB_NAME,),
            )

            cur.execute(
                sql.SQL("DROP DATABASE {}").format(
                    sql.Identifier(EVALUATION_DB_NAME)
                )
            )

    print(
        "[OK] evaluation database dropped: "
        f"{EVALUATION_DB_NAME}"
    )


def main() -> None:
    drop_evaluation_database()


if __name__ == "__main__":
    main()
