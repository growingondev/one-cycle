import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.models.processing_run import ProcessingRun
from backend.app.models.system_state import SystemState
from backend.app.services import collection_retention_service as retention


@pytest.fixture
def retained_dataset(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    for model in (
        CollectionRun,
        Announcement,
        Document,
        ProcessingRun,
        SystemState,
    ):
        model.__table__.create(engine)

    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    document_root = tmp_path / "documents"
    output_root = tmp_path / "outputs"
    document_root.mkdir()
    output_root.mkdir()
    monkeypatch.setattr(retention, "SessionLocal", sessions)
    monkeypatch.setattr(retention.settings, "crawler_staging_dir", str(document_root))
    monkeypatch.setattr(
        retention.settings,
        "collection_retention_output_root",
        str(output_root),
    )
    for setting_name in (
        "collection_retention_legacy_document_stored_root",
        "collection_retention_legacy_document_access_root",
        "collection_retention_legacy_output_stored_root",
        "collection_retention_legacy_output_access_root",
    ):
        monkeypatch.setattr(
            retention.settings,
            setting_name,
            "",
        )

    run_ids = []
    document_paths = {}
    output_paths = {}
    with sessions.begin() as db:
        for index, status in enumerate(
            ("success", "success", "success", "running"),
            start=1,
        ):
            run = CollectionRun(
                execution_id=f"run-{index}",
                status=status,
            )
            db.add(run)
            db.flush()
            run_ids.append(run.id)

            announcement = Announcement(
                collection_run_id=run.id,
                source_announcement_id=f"A-{index}",
                title=f"공고 {index}",
                detail_url=f"https://example.test/{index}",
            )
            db.add(announcement)
            db.flush()

            document_path = document_root / f"run-{index}" / "notice.hwpx"
            document_path.parent.mkdir()
            document_path.write_text(f"notice {index}", encoding="utf-8")
            document_paths[run.id] = document_path
            document = Document(
                announcement_id=announcement.id,
                original_filename="notice.hwpx",
                document_format="hwpx",
                document_role="primary",
                storage_path=str(document_path),
                download_status="completed",
            )
            db.add(document)
            db.flush()

            output_path = output_root / f"run-{index}" / f"document-{document.id}"
            output_path.mkdir(parents=True)
            (output_path / "result.json").write_text("{}", encoding="utf-8")
            output_paths[run.id] = output_path
            db.add(
                ProcessingRun(
                    document_id=document.id,
                    execution_status="failed",
                    verification_status="fail",
                    output_root_path=str(output_path),
                )
            )

        db.add(
            SystemState(
                id=1,
                active_collection_run_id=run_ids[2],
                previous_collection_run_id=run_ids[1],
            )
        )

    yield sessions, run_ids, document_paths, output_paths
    engine.dispose()


def test_dry_run_does_not_delete_db_or_files(retained_dataset):
    sessions, run_ids, document_paths, output_paths = retained_dataset

    result = retention.apply_collection_run_retention(dry_run=True)

    assert result["status"] == "dry_run"
    assert result["candidate_run_ids"] == [run_ids[0]]
    assert result["skipped_running_run_ids"] == [run_ids[3]]
    with sessions() as db:
        assert db.scalar(select(func.count(CollectionRun.id))) == 4
    assert all(path.exists() for path in document_paths.values())
    assert all(path.exists() for path in output_paths.values())


def test_delete_keeps_active_previous_and_running(retained_dataset):
    sessions, run_ids, document_paths, output_paths = retained_dataset

    result = retention.apply_collection_run_retention(dry_run=False)

    assert result["status"] == "completed"
    assert result["deleted_run_count"] == 1
    with sessions() as db:
        assert list(db.scalars(select(CollectionRun.id).order_by(CollectionRun.id))) == [
            run_ids[1],
            run_ids[2],
            run_ids[3],
        ]
        state = db.get(SystemState, 1)
        assert state.active_collection_run_id == run_ids[2]
        assert state.previous_collection_run_id == run_ids[1]
    assert not document_paths[run_ids[0]].exists()
    assert not output_paths[run_ids[0]].exists()
    assert all(document_paths[run_id].exists() for run_id in run_ids[1:])
    assert all(output_paths[run_id].exists() for run_id in run_ids[1:])


def test_missing_previous_run_blocks_cleanup(retained_dataset):
    sessions, _, document_paths, _ = retained_dataset
    with sessions.begin() as db:
        db.get(SystemState, 1).previous_collection_run_id = None

    result = retention.apply_collection_run_retention(dry_run=False)

    assert result["status"] == "skipped"
    assert result["reason"] == "previous_collection_run_not_initialized"
    with sessions() as db:
        assert db.scalar(select(func.count(CollectionRun.id))) == 4
    assert all(path.exists() for path in document_paths.values())


def test_path_outside_allowed_root_blocks_db_deletion(retained_dataset, tmp_path):
    sessions, run_ids, _, _ = retained_dataset
    outside = tmp_path / "outside.hwpx"
    outside.write_text("keep", encoding="utf-8")
    with sessions.begin() as db:
        document = db.scalar(
            select(Document)
            .join(Announcement)
            .where(Announcement.collection_run_id == run_ids[0])
        )
        document.storage_path = str(outside)

    result = retention.apply_collection_run_retention(dry_run=False)

    assert result["status"] == "file_cleanup_incomplete"
    assert result["deleted_run_count"] == 0
    assert str(outside) in result["unsafe_paths"]
    assert outside.exists()
    with sessions() as db:
        assert db.get(CollectionRun, run_ids[0]) is not None

def test_delete_maps_legacy_stored_paths_to_access_roots(
    retained_dataset,
    tmp_path,
    monkeypatch,
):
    sessions, run_ids, document_paths, output_paths = retained_dataset
    candidate_run_id = run_ids[0]

    stored_document_root = tmp_path / "legacy-stored-documents"
    access_document_root = tmp_path / "legacy-access-documents"
    stored_output_root = tmp_path / "legacy-stored-outputs"
    access_output_root = tmp_path / "legacy-access-outputs"
    access_document_root.mkdir()
    access_output_root.mkdir()

    original_document_path = document_paths[candidate_run_id]
    relative_document_path = original_document_path.relative_to(
        original_document_path.parents[1]
    )
    accessible_document_path = (
        access_document_root / relative_document_path
    )
    accessible_document_path.parent.mkdir(parents=True)
    original_document_path.replace(accessible_document_path)

    original_output_path = output_paths[candidate_run_id]
    relative_output_path = original_output_path.relative_to(
        original_output_path.parents[1]
    )
    accessible_output_path = access_output_root / relative_output_path
    accessible_output_path.parent.mkdir(parents=True)
    original_output_path.replace(accessible_output_path)

    with sessions.begin() as db:
        document = db.scalar(
            select(Document)
            .join(Announcement)
            .where(Announcement.collection_run_id == candidate_run_id)
        )
        processing_run = db.scalar(
            select(ProcessingRun)
            .join(Document)
            .join(Announcement)
            .where(Announcement.collection_run_id == candidate_run_id)
        )
        document.storage_path = str(
            stored_document_root / relative_document_path
        )
        processing_run.output_root_path = str(
            stored_output_root / relative_output_path
        )

    monkeypatch.setattr(
        retention.settings,
        "collection_retention_legacy_document_stored_root",
        str(stored_document_root),
    )
    monkeypatch.setattr(
        retention.settings,
        "collection_retention_legacy_document_access_root",
        str(access_document_root),
    )
    monkeypatch.setattr(
        retention.settings,
        "collection_retention_legacy_output_stored_root",
        str(stored_output_root),
    )
    monkeypatch.setattr(
        retention.settings,
        "collection_retention_legacy_output_access_root",
        str(access_output_root),
    )

    result = retention.apply_collection_run_retention(dry_run=False)

    assert result["status"] == "completed"
    assert result["unsafe_paths"] == []
    assert result["deleted_run_count"] == 1
    assert not accessible_document_path.exists()
    assert not accessible_output_path.exists()
    with sessions() as db:
        assert db.get(CollectionRun, candidate_run_id) is None


def test_incomplete_legacy_mapping_blocks_plan(
    retained_dataset,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        retention.settings,
        "collection_retention_legacy_document_stored_root",
        str(tmp_path / "legacy-stored-documents"),
    )

    with pytest.raises(RuntimeError, match="configured together"):
        retention.plan_collection_run_retention()

