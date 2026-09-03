import unittest

from crawler.crawler import (
    _extract_notice_summary,
    _safe_download_filename,
)


class _Cell:
    def __init__(self, text):
        self.text = text


class _Row:
    def __init__(self):
        self.cells = [
            _Cell("123"),
            _Cell("매입임대"),
            _Cell(""),
            _Cell("서울"),
            _Cell(""),
            _Cell("2026.09.03"),
            _Cell("2026.09.15"),
            _Cell("접수중"),
        ]

    def find_elements(self, *_args):
        return self.cells


class _NoticeElement:
    text = "[정정공고] 청년 매입임대"

    def __init__(self):
        self.row = _Row()
        self.attributes = {
            "data-id1": "LH-001",
            "data-id2": "CCR",
            "data-id3": "UPP",
            "data-id4": "AIS",
        }

    def get_attribute(self, name):
        return self.attributes.get(name)

    def find_element(self, *_args):
        return self.row


class CrawlerScanTest(unittest.TestCase):
    def test_extract_notice_summary_returns_serializable_metadata(self):
        result = _extract_notice_summary(_NoticeElement())

        self.assertEqual(result["source_announcement_id"], "LH-001")
        self.assertEqual(result["notice_number"], "123")
        self.assertEqual(result["notice_type"], "매입임대")
        self.assertEqual(result["region"], "서울")
        self.assertEqual(result["post_date"], "2026.09.03")
        self.assertEqual(result["deadline_date"], "2026.09.15")
        self.assertEqual(result["publication_status"], "접수중")
        self.assertIn("panId=LH-001", result["detail_url"])

    def test_safe_filename_removes_remote_path(self):
        self.assertEqual(
            _safe_download_filename("../../공고문.hwpx"),
            "공고문.hwpx",
        )


if __name__ == "__main__":
    unittest.main()
