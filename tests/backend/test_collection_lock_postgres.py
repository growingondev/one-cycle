"""Opt-in real PostgreSQL/process tests, isolated from production.

Set ONE_CYCLE_TEST_POSTGRES_URL to a loopback DB named restore_test*.
Admin requests use the real ASGI route in a separate process; Scheduler uses its
real callback in another process. Only the slow external pipeline is simulated.
"""

import multiprocessing
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _entry_process(url, entry, outcome, gates, messages):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app import scheduler
    from backend.app.api.dependencies import get_current_admin
    from backend.app.api.routes import admin
    from backend.app.services import pipeline_gateway

    engine = create_engine(url, pool_pre_ping=True)
    pipeline_gateway.engine = engine
    called = False

    def runner():
        nonlocal called
        called = True
        for index, phase in enumerate(("crawl", "processing", "publish")):
            messages.put(("phase", phase))
            if gates and not gates[index].wait(20):
                raise RuntimeError("test phase timed out")
        if outcome == "exception":
            raise RuntimeError("simulated pipeline exception")
        return {"status": "failed" if outcome == "failed" else "success"}

    pipeline_gateway._load_callable = lambda _: runner
    try:
        if entry == "admin":
            app = FastAPI()
            app.include_router(admin.router, prefix="/api")
            app.dependency_overrides[get_current_admin] = lambda: object()
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/api/admin/announcements/collect")
            messages.put(("result", response.status_code))
        else:
            scheduler.run_scheduled_sync()
            messages.put(("result", "ran" if called else "skipped"))
    finally:
        engine.dispose()


@pytest.fixture
def postgres_url():
    value = os.getenv("ONE_CYCLE_TEST_POSTGRES_URL", "")
    if not value:
        pytest.skip("Set ONE_CYCLE_TEST_POSTGRES_URL for isolated PostgreSQL tests")
    parsed = make_url(value)
    if parsed.host not in {"127.0.0.1", "localhost"} or not (
        parsed.database or ""
    ).startswith("restore_test"):
        pytest.fail("Refusing non-local/non-test PostgreSQL database")
    return value


@pytest.mark.parametrize(
    "first,second", [("admin", "scheduler"), ("scheduler", "admin")]
)
@pytest.mark.parametrize("outcome", ["success", "failed", "exception"])
def test_real_process_lock_spans_pipeline_and_releases(
    postgres_url, first, second, outcome
):
    context = multiprocessing.get_context("spawn")
    gates = [context.Event() for _ in range(3)]
    first_messages = context.Queue()
    second_messages = context.Queue()
    holder = context.Process(
        target=_entry_process,
        args=(postgres_url, first, outcome, gates, first_messages),
    )
    contender = context.Process(
        target=_entry_process,
        args=(postgres_url, second, "success", None, second_messages),
    )
    processes = [holder, contender]
    engine = create_engine(postgres_url)

    def lock_rows():
        with engine.connect() as db:
            return db.execute(
                text(
                    "SELECT l.pid, a.state FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
                    "WHERE l.locktype = 'advisory' AND l.objid = 615120315 AND l.granted"
                )
            ).all()

    try:
        assert lock_rows() == []
        holder.start()
        assert first_messages.get(timeout=20) == ("phase", "crawl")
        rows = lock_rows()
        assert len(rows) == 1 and rows[0].state == "idle"  # not idle in transaction
        lock_pid = rows[0].pid
        contender.start()
        assert second_messages.get(timeout=20) == (
            "result",
            409 if second == "admin" else "skipped",
        )
        contender.join(10)
        assert contender.exitcode == 0
        for index, phase in enumerate(("processing", "publish")):
            gates[index].set()
            assert first_messages.get(timeout=20) == ("phase", phase)
            assert [(row.pid, row.state) for row in lock_rows()] == [(lock_pid, "idle")]
        gates[2].set()
        expected = (201 if outcome == "success" else 500) if first == "admin" else "ran"
        assert first_messages.get(timeout=20) == ("result", expected)
        holder.join(10)
        assert holder.exitcode == 0
        assert lock_rows() == []

        # A fresh process can acquire the same lock after success/failure/exception.
        recovery_messages = context.Queue()
        recovery = context.Process(
            target=_entry_process,
            args=(postgres_url, "admin", "success", None, recovery_messages),
        )
        processes.append(recovery)
        recovery.start()
        for phase in ("crawl", "processing", "publish"):
            assert recovery_messages.get(timeout=20) == ("phase", phase)
        assert recovery_messages.get(timeout=20) == ("result", 201)
        recovery.join(10)
        assert recovery.exitcode == 0
        assert lock_rows() == []
    finally:
        for gate in gates:
            gate.set()
        for process in processes:
            if process.pid is not None:
                process.join(5)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
        engine.dispose()
