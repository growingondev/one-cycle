from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from crawler import crawler


@pytest.mark.parametrize("partial", [False, True])
def test_first_page_is_fully_processed_and_only_temp_is_cleaned(
    tmp_path, monkeypatch, partial
):
    monkeypatch.setenv("CRAWLER_STAGING_DIR", str(tmp_path))
    notices = []
    for index in range(3):
        notice = Mock()
        notice.text = f"공고 {index}"
        notice.get_attribute.side_effect = lambda key, i=index: {
            "data-id1": f"NOTICE-{i}",
            "data-id2": "02",
            "data-id3": "06",
            "data-id4": "07",
        }.get(key)
        notice.find_element.return_value.find_elements.return_value = [
            SimpleNamespace(text=value)
            for value in (
                str(index),
                "임대",
                "제목",
                "서울",
                "",
                "2026.09.04",
                "2026.09.30",
                "공고중",
            )
        ]
        notices.append(notice)
    driver = Mock()
    paths = []

    def process(driver, temp, execution, **kwargs):
        assert Path(temp).is_dir()
        source = kwargs["source_announcement_id_override"]
        destination = Path(execution) / source / "공고문.hwpx"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"downloaded")
        paths.append(destination)
        return {
            **kwargs["meta_override"],
            "source_announcement_id": source,
            "documents": [],
            "errors": [],
            "is_success": not (partial and source == "NOTICE-1"),
        }

    with (
        patch.object(crawler, "create_driver", return_value=driver),
        patch.object(crawler, "close_main_popup"),
        patch.object(crawler, "click_allow_popup"),
        patch.object(crawler.time, "sleep"),
        patch.object(crawler, "WebDriverWait") as wait,
        patch.object(
            crawler, "wait_for_notice_element", side_effect=notices
        ) as restored,
        patch.object(crawler, "_process_single_notice", side_effect=process),
    ):
        wait.return_value.until.side_effect = [Mock(), Mock(), Mock(), notices]
        result = crawler.crawl_lh_notices()
    assert result["execution_status"] == ("partial" if partial else "success")
    assert result["total_count"] == 3
    assert result["success_count"] == (2 if partial else 3)
    assert restored.call_count == 3
    assert driver.back.call_count == 3
    assert all(call.kwargs["expected_total"] == 3 for call in restored.call_args_list)
    assert all(path.is_file() for path in paths)
    assert all(
        path.parent.parent == tmp_path / result["execution_id"] for path in paths
    )
    assert not (tmp_path / result["execution_id"] / "_temp_download").exists()
    driver.quit.assert_called_once_with()


def test_recollection_keeps_download_and_passes_target_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("CRAWLER_STAGING_DIR", str(tmp_path))
    driver = Mock()
    captured = []

    def process(driver, temp, execution, **kwargs):
        path = Path(execution) / "A" / "공고문.hwpx"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"download")
        captured.append(path)
        assert kwargs["target_file_name"] == "공고문.hwpx"
        return {"documents": [], "errors": [], "is_success": True}

    with (
        patch.object(crawler, "create_driver", return_value=driver),
        patch.object(crawler, "click_allow_popup"),
        patch.object(crawler.time, "sleep"),
        patch.object(crawler, "WebDriverWait"),
        patch.object(crawler, "_process_single_notice", side_effect=process),
    ):
        result = crawler.recollect_lh_notice(
            "A", "https://example.test/A", target_file_name="공고문.hwpx"
        )
    assert result["status"] == "success"
    assert captured[0].is_file()
    assert captured[0].parent.parent == tmp_path / result["execution_id"]
    assert not (tmp_path / result["execution_id"] / "_temp_download").exists()


def test_same_attachment_name_on_different_notices_has_separate_paths(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CRAWLER_STAGING_DIR", str(tmp_path))
    execution = tmp_path / "execution_test"
    temp = execution / "_temp_download"
    temp.mkdir(parents=True)
    driver = Mock()
    driver.current_url = "https://example.test"
    attachment = SimpleNamespace(text="공고문.hwpx")
    driver.find_elements.return_value = [attachment]
    payload = [b"A-file", b"B-file"]

    def download(*args, **kwargs):
        (temp / "download.hwpx").write_bytes(payload.pop(0))
        return ["download.hwpx"]

    with (
        patch.object(crawler, "WebDriverWait") as wait,
        patch.object(crawler, "click_allow_popup"),
        patch.object(crawler.time, "sleep"),
        patch.object(crawler, "wait_for_download_start", side_effect=download),
    ):
        wait.return_value.until.return_value = [attachment]
        for source in ("A", "B"):
            result = crawler._process_single_notice(
                driver, temp, execution, source_announcement_id_override=source
            )
            assert result["is_success"]
            assert result["documents"][0]["storage_path"] == str(
                execution / source / attachment.text
            )
    assert (execution / "A" / attachment.text).read_bytes() == b"A-file"
    assert (execution / "B" / attachment.text).read_bytes() == b"B-file"


def test_cleanup_refuses_execution_root_and_outside_folder(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir()
    monkeypatch.setenv("CRAWLER_STAGING_DIR", str(root))
    execution = root / "execution_test"
    execution.mkdir()
    outside = tmp_path / "_temp_download"
    outside.mkdir()
    for unsafe in (root, execution, outside):
        with pytest.raises(ValueError):
            crawler.cleanup_temp_directory(unsafe)
        assert unsafe.is_dir()


def test_execution_ids_are_unique_even_with_same_timestamp():
    assert len({crawler._new_execution_id("execution") for _ in range(100)}) == 100


def test_unsafe_notice_ids_cannot_collide_or_escape_storage():
    assert crawler._safe_storage_component("../A") != crawler._safe_storage_component(
        "A"
    )
    assert crawler._safe_storage_component("A/B") != crawler._safe_storage_component(
        "A_B"
    )
    assert "/" not in crawler._safe_storage_component("../A")
