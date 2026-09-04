from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from document_worker import service
from document_worker.api.schemas import (
    DocumentProcessRequest,
)


def _key_information() -> dict[str, dict[str, str]]:
    return {
        field: {"status": "found"}
        for field in service.REQUIRED_FIELDS
    }


class DocumentWorkerRetryTest(unittest.TestCase):

    def test_embedding_retry_skips_successful_previous_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "root": root,
                "parsed": root / "parsed.json",
                "normalized": root / "normalized.json",
                "structured_dir": root,
                "structure": root / "structure.json",
                "verification": root / "verification.json",
                "chunks": root / "chunks.json",
                "embeddings_dir": root,
                "embeddings": root / "embeddings.npy",
                "embedding_metadata": root / "metadata.json",
                "embedding_report": root / "report.json",
            }
            for key in (
                "parsed",
                "normalized",
                "structure",
                "verification",
                "chunks",
            ):
                paths[key].touch()

            request = DocumentProcessRequest(
                announcement_id=3,
                announcement_key="NOTICE-3",
                announcement_date=date(2026, 9, 3),
                source={
                    "filename": "notice.hwpx",
                    "format": "hwpx",
                    "storage_path": str(root / "notice.hwpx"),
                },
                start_stage="embedding",
            )
            vectors = np.zeros((2, 1024), dtype=np.float32)
            chunk_document = SimpleNamespace(chunk_count=2)

            with (
                patch.object(
                    service,
                    "_resolve_source_path",
                    return_value=root / "notice.hwpx",
                ),
                patch.object(
                    service,
                    "_validate_document_format",
                    return_value="hwpx",
                ),
                patch.object(
                    service,
                    "_prepare_stage_paths",
                    return_value=paths,
                ),
                patch.object(service, "_run_parser") as parser,
                patch.object(service, "_run_normalizer") as normalizer,
                patch.object(service, "_run_structure") as structure,
                patch.object(service, "_run_chunking") as chunking,
                patch.object(
                    service,
                    "_run_embedding_service",
                    return_value=(chunk_document, vectors),
                ) as embedding,
                patch.object(service, "_write_embedding_artifacts"),
                patch.object(
                    service,
                    "_run_key_information_extraction",
                    return_value=_key_information(),
                ) as key_information,
            ):
                response = service.process_document(
                    document_id=9,
                    request=request,
                )

            parser.assert_not_called()
            normalizer.assert_not_called()
            structure.assert_not_called()
            chunking.assert_not_called()
            embedding.assert_called_once()
            self.assertEqual(
                key_information.call_args.kwargs[
                    "announcement_date"
                ],
                date(2026, 9, 3),
            )
            self.assertEqual(response.status, "completed")
            self.assertEqual(response.summary.embedding_count, 2)


if __name__ == "__main__":
    unittest.main()
