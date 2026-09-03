from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from crawler import crawler


class CrawlerTargetRetryTest(unittest.TestCase):

    @patch.object(crawler, "click_allow_popup")
    @patch.object(crawler, "wait_for_download_start", return_value=[])
    @patch.object(crawler, "WebDriverWait")
    def test_only_matching_attachment_is_clicked(
        self,
        web_driver_wait,
        _wait_for_download_start,
        _click_allow_popup,
    ):
        skipped = SimpleNamespace(text="other.hwp")
        target = SimpleNamespace(text="failed.hwpx")
        web_driver_wait.return_value.until.return_value = [
            skipped,
            target,
        ]

        driver = Mock()
        driver.current_url = "https://example.com/notice?panId=NOTICE-1"
        driver.find_elements.return_value = [skipped, target]

        with tempfile.TemporaryDirectory() as directory:
            result = crawler._process_single_notice(
                driver,
                Path(directory),
                Path(directory),
                source_announcement_id_override="NOTICE-1",
                detail_url_override=driver.current_url,
                target_file_name="failed.hwpx",
            )

        driver.execute_script.assert_called_once_with(
            "arguments[0].click();",
            target,
        )
        self.assertFalse(result["is_success"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(
            result["errors"][0]["file_name"],
            "failed.hwpx",
        )


if __name__ == "__main__":
    unittest.main()
