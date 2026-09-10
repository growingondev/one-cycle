from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from selenium.webdriver.common.by import By

from crawler import crawler


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("공고문", "primary"),
        ("  • 공고문 : ", "primary"),
        ("다운로드", "supporting"),
        (" 다운로드 : ", "supporting"),
        ("첨부파일", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_document_role_is_determined_only_by_area_label(
    label,
    expected,
):
    assert crawler._document_role_from_area_label(label) == expected


def _attachment_block(label, links):
    block = Mock()
    block.find_element.return_value = SimpleNamespace(text=label)
    block.find_elements.return_value = links
    return block


def test_attachment_candidates_keep_each_dom_area_role():
    primary_links = [
        SimpleNamespace(text="공급주택목록요약.hwpx"),
        SimpleNamespace(text="이름이애매한문서.hwp"),
    ]
    supporting_links = [
        SimpleNamespace(text="입주자모집공고문.hwpx"),
        SimpleNamespace(text="Q&A.hwpx"),
    ]
    unknown_links = [
        SimpleNamespace(text="기타.hwpx"),
    ]

    primary_block = _attachment_block(
        "공고문",
        primary_links,
    )
    supporting_block = _attachment_block(
        "다운로드",
        supporting_links,
    )
    unknown_block = _attachment_block(
        "첨부파일",
        unknown_links,
    )

    driver = Mock()
    driver.find_elements.return_value = [
        primary_block,
        supporting_block,
        unknown_block,
    ]

    assert crawler._find_attachment_candidates(driver) == [
        (primary_links[0], "primary"),
        (primary_links[1], "primary"),
        (supporting_links[0], "supporting"),
        (supporting_links[1], "supporting"),
        (unknown_links[0], "unknown"),
    ]

    driver.find_elements.assert_called_once_with(
        By.CSS_SELECTOR,
        crawler.ATTACHMENT_BLOCK_SELECTOR,
    )
    for block in (
        primary_block,
        supporting_block,
        unknown_block,
    ):
        block.find_element.assert_called_once_with(
            By.XPATH,
            "./ancestor::dl[1]/dt[1]",
        )
        block.find_elements.assert_called_once_with(
            By.CSS_SELECTOR,
            crawler.ATTACHMENT_DOWNLOAD_LINK_SELECTOR,
        )


def test_missing_area_heading_returns_unknown():
    block = Mock()
    block.find_element.side_effect = RuntimeError(
        "area heading not found"
    )

    assert (
        crawler._document_role_for_attachment_block(block)
        == "unknown"
    )


def test_processed_documents_keep_dom_roles_and_existing_metadata(
    tmp_path,
):
    execution_dir = tmp_path / "execution_test"
    temp_dir = execution_dir / "_temp_download"
    temp_dir.mkdir(parents=True)

    primary_link = SimpleNamespace(
        text="공급주택목록요약.hwpx"
    )
    supporting_link = SimpleNamespace(
        text="입주자모집공고문.hwpx"
    )
    candidates = [
        (primary_link, "primary"),
        (supporting_link, "supporting"),
    ]
    downloads = iter(
        [
            ("first.hwpx", b"primary-file"),
            ("second.hwpx", b"supporting-file"),
        ]
    )

    def start_download(download_dir, _before_files):
        name, payload = next(downloads)
        (Path(download_dir) / name).write_bytes(payload)
        return [name]

    driver = Mock()
    driver.current_url = (
        "https://example.com/notice?panId=NOTICE-1"
    )

    with (
        patch.object(crawler, "WebDriverWait") as wait,
        patch.object(
            crawler,
            "_find_attachment_candidates",
            return_value=candidates,
        ),
        patch.object(
            crawler,
            "wait_for_download_start",
            side_effect=start_download,
        ),
        patch.object(crawler, "click_allow_popup"),
        patch.object(crawler.time, "sleep"),
    ):
        wait.return_value.until.return_value = candidates
        result = crawler._process_single_notice(
            driver,
            temp_dir,
            execution_dir,
            source_announcement_id_override="NOTICE-1",
        )

    assert result["is_success"] is True
    assert [
        document["document_role"]
        for document in result["documents"]
    ] == ["primary", "supporting"]
    assert [
        document["download_status"]
        for document in result["documents"]
    ] == ["completed", "completed"]
    assert all(
        document["checksum_sha256"]
        for document in result["documents"]
    )
    assert result["documents"][0]["storage_path"] == str(
        execution_dir
        / "NOTICE-1"
        / primary_link.text
    )
    assert result["documents"][1]["storage_path"] == str(
        execution_dir
        / "NOTICE-1"
        / supporting_link.text
    )


def test_targeted_recollection_preserves_supporting_role(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "CRAWLER_STAGING_DIR",
        str(tmp_path),
    )
    document = {
        "file_name": "입주자모집공고문.hwpx",
        "file_format": "hwpx",
        "storage_path": "/data/documents/notice.hwpx",
        "file_size_bytes": 100,
        "checksum_sha256": "checksum",
        "download_status": "completed",
        "error_message": None,
        "document_role": "supporting",
    }
    driver = Mock()

    with (
        patch.object(
            crawler,
            "create_driver",
            return_value=driver,
        ),
        patch.object(crawler, "close_main_popup"),
        patch.object(crawler, "click_allow_popup"),
        patch.object(
            crawler,
            "_process_single_notice",
            return_value={
                "documents": [document],
                "errors": [],
                "is_success": True,
            },
        ),
    ):
        result = crawler.recollect_lh_notice(
            "NOTICE-1",
            "https://example.com/notice/1",
            target_file_name=document["file_name"],
        )

    assert result["status"] == "success"
    assert result["data"]["documents"] == [document]
    assert (
        result["data"]["documents"][0]["document_role"]
        == "supporting"
    )
