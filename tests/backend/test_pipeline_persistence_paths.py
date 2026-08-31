from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app.services.pipeline_persistence import (
    _resolve_bundle_root,
)


class PipelinePersistencePathTest(
    unittest.TestCase
):
    def test_default_output_root_is_preserved(
        self,
    ):
        result = _resolve_bundle_root(
            announcement_key="LH-TEST-001",
            document_id=30,
            output_root_path=None,
        )

        self.assertEqual(
            result.name,
            "document_30",
        )
        self.assertEqual(
            result.parent.name,
            "LH-TEST-001",
        )

    def test_native_absolute_output_path_is_accepted(
        self,
    ):
        with TemporaryDirectory() as temp_dir:
            root = (
                Path(temp_dir)
                / "LH-TEST-001"
                / "document_30"
            )

            result = _resolve_bundle_root(
                announcement_key="LH-TEST-001",
                document_id=30,
                output_root_path=str(root),
            )

        self.assertEqual(
            result,
            root.resolve(),
        )

    def test_document_id_mismatch_is_rejected(
        self,
    ):
        with TemporaryDirectory() as temp_dir:
            root = (
                Path(temp_dir)
                / "LH-TEST-001"
                / "document_31"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "document_id",
            ):
                _resolve_bundle_root(
                    announcement_key="LH-TEST-001",
                    document_id=30,
                    output_root_path=str(root),
                )

    def test_announcement_key_mismatch_is_rejected(
        self,
    ):
        with TemporaryDirectory() as temp_dir:
            root = (
                Path(temp_dir)
                / "LH-OTHER"
                / "document_30"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "announcement_key",
            ):
                _resolve_bundle_root(
                    announcement_key="LH-TEST-001",
                    document_id=30,
                    output_root_path=str(root),
                )

    def test_relative_output_path_is_rejected(
        self,
    ):
        with self.assertRaisesRegex(
            RuntimeError,
            "절대 경로",
        ):
            _resolve_bundle_root(
                announcement_key="LH-TEST-001",
                document_id=30,
                output_root_path=(
                    "outputs/"
                    "LH-TEST-001/"
                    "document_30"
                ),
            )

    def test_docker_posix_path_is_not_rewritten_on_windows(
        self,
    ):
        with patch(
            "backend.app.services."
            "pipeline_persistence.os.name",
            "nt",
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Docker POSIX output_path",
            ):
                _resolve_bundle_root(
                    announcement_key="LH-TEST-001",
                    document_id=30,
                    output_root_path=(
                        "/data/outputs/"
                        "LH-TEST-001/"
                        "document_30"
                    ),
                )

    def test_docker_path_identity_is_checked_before_access(
        self,
    ):
        with patch(
            "backend.app.services."
            "pipeline_persistence.os.name",
            "nt",
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "document_id",
            ):
                _resolve_bundle_root(
                    announcement_key="LH-TEST-001",
                    document_id=30,
                    output_root_path=(
                        "/data/outputs/"
                        "LH-TEST-001/"
                        "document_99"
                    ),
                )


if __name__ == "__main__":
    unittest.main()