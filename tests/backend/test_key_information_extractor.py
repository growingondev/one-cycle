import unittest

from pipeline.key_information_extractor import (
    _build_application_period,
    _build_eligibility,
    _build_income_asset_criteria,
    _build_required_documents,
    _build_supply_information,
)


def make_match(text: str):
    return {
        "section_id": "test",
        "title": "test",
        "section_path": ["test"],
        "domain": {},
        "score": 10,
        "text": text,
        "_section": {},
    }


class KeyInformationExtractorTest(unittest.TestCase):
    def test_application_period(self):
        text = (
            "\uC2E0\uCCAD\uC811\uC218\n"
            "2026.08.27.(\uBAA9) 10:00\n"
            "~2026.08.28.(\uAE08) 17:00\n"
            "\uC11C\uB958\uC81C\uCD9C\n"
            "2026.09.08.(\uD654)\n"
            "~2026.09.10.(\uBAA9)"
        )

        result = _build_application_period(
            [make_match(text)]
        )

        self.assertEqual(
            result["start"],
            "2026-08-27 10:00",
        )
        self.assertEqual(
            result["end"],
            "2026-08-28 17:00",
        )

    def test_application_period_korean_ampm_range(
            self,
        ):
            text = (
                "인터넷(PC) 청약 접수기간은 "
                "접수시작일 ‘26.08.27(목) "
                "오전 10시부터 "
                "마감일 ’26.08.28(금) "
                "오후 5시까지로 "
                "접수기간 중에는 "
                "24시간 신청 가능합니다."
            )

            result = _build_application_period(
                [make_match(text)]
            )

            self.assertEqual(
                result["start"],
                "2026-08-27 10:00",
            )
            self.assertEqual(
                result["end"],
                "2026-08-28 17:00",
            )
            self.assertEqual(
                result["summary"],
                (
                    "2026-08-27 10:00"
                    " ~ "
                    "2026-08-28 17:00"
                ),
            )

    def test_application_period_labeled_range(
            self,
        ):
            text = (
                "신청기간 "
                "접수시작일 "
                "2026.08.27 10:00 "
                "마감일 "
                "2026.08.28 17:00"
            )

            result = _build_application_period(
                [make_match(text)]
            )

            self.assertEqual(
                result["start"],
                "2026-08-27 10:00",
            )
            self.assertEqual(
                result["end"],
                "2026-08-28 17:00",
            )

    def test_eligibility_summary(self):
        text = (
            "\uC2E0\uCCAD\uC790\uACA9\n"
            "\uBAA8\uC9D1\uACF5\uACE0\uC77C "
            "\uD604\uC7AC \uB9CC19\uC138 "
            "\uC774\uC0C1 "
            "\uBB34\uC8FC\uD0DD\uC138\uB300\uAD6C\uC131\uC6D0"
        )

        result = _build_eligibility(
            [make_match(text)]
        )

        self.assertIn(
            "\uBB34\uC8FC\uD0DD",
            result["summary"],
        )

    def test_income_asset_summary(self):
        text = (
            "\uC18C\uB4DD\uAE30\uC900 \uBC0F "
            "\uC790\uC0B0\uAE30\uC900\uC5D0 "
            "\uAD00\uACC4\uC5C6\uC774 "
            "\uC2E0\uCCAD\uAC00\uB2A5"
        )

        result = _build_income_asset_criteria(
            [make_match(text)]
        )

        self.assertIn(
            "\uAD00\uACC4\uC5C6\uC774",
            result["summary"],
        )

    def test_supply_summary_is_compact(self):
        text = (
            "\uACF5\uAE09\uB300\uC0C1\n"
            "\uB300\uAD6C \uAE08\uD638 6\uB2E8\uC9C0 "
            "904\uC138\uB300, "
            "\uC608\uBE44\uC785\uC8FC\uC790 355\uC138\uB300\n"
            "\uB300\uAD6C \uC5F0\uACBD\uC232 "
            "823\uC138\uB300, "
            "\uC608\uBE44\uC785\uC8FC\uC790 210\uC138\uB300\n"
            + ("extra " * 500)
        )

        result = _build_supply_information(
            [make_match(text)]
        )

        self.assertIn(
            "355",
            result["summary"],
        )
        self.assertLess(
            len(result["summary"]),
            400,
        )

    def test_required_documents(self):
        text = (
            "\uC81C\uCD9C\uC11C\uB958: "
            "\uC8FC\uBBFC\uB4F1\uB85D\uD45C\uB4F1\uBCF8, "
            "\uAC00\uC871\uAD00\uACC4\uC99D\uBA85\uC11C, "
            "\uC2E0\uBD84\uC99D"
        )

        result = _build_required_documents(
            [make_match(text)]
        )

        self.assertIn(
            "\uC8FC\uBBFC\uB4F1\uB85D\uB4F1\uBCF8",
            result["items"],
        )
        self.assertIn(
            "\uAC00\uC871\uAD00\uACC4\uC99D\uBA85\uC11C",
            result["items"],
        )


if __name__ == "__main__":
    unittest.main()
