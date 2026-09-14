import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.services.pipeline_persistence import (
    persist_outputs,
)


class PipelinePersistenceDocumentLookupTest(
    unittest.TestCase
):
    def test_document_id_lookup_omits_format_filter(
        self,
    ):
        db = MagicMock()
        db.execute.return_value.all.return_value = []

        summary = {
            "announcement_key": "LH-TEST-001",
            "format": "hwp",
            "filename": "sample.hwpx",
        }

        bundle = {
            "root": Path("/app/outputs/test"),
            "structure": Path("structure.json"),
            "chunks": Path("chunks.json"),
            "metadata": Path("metadata.json"),
            "embeddings": Path("embeddings.npy"),
        }

        with (
            patch(
                "backend.app.services."
                "pipeline_persistence.validate_outputs",
                return_value=summary,
            ),
            patch(
                "backend.app.services."
                "pipeline_persistence.find_bundle",
                return_value=bundle,
            ),
            patch(
                "backend.app.services."
                "pipeline_persistence.load_json",
                side_effect=[{}, {}, {}],
            ),
            patch(
                "backend.app.services."
                "pipeline_persistence.np.load",
                return_value=MagicMock(),
            ),
            patch(
                "backend.app.services."
                "pipeline_persistence.SessionLocal",
            ) as session_local,
        ):
            session_local.begin.return_value.__enter__.return_value = db

            with self.assertRaisesRegex(
                RuntimeError,
                "actual=0",
            ):
                persist_outputs(
                    "LH-TEST-001",
                    document_id=3431,
                )

        statement = db.execute.call_args.args[0]
        sql = str(
            statement.compile(
                compile_kwargs={
                    "literal_binds": True,
                }
            )
        )

        where_clause = sql.split(
            "\nWHERE ",
            maxsplit=1,
        )[1]

        self.assertIn(
            "documents.id = 3431",
            where_clause,
        )
        self.assertNotIn(
            "documents.document_format",
            where_clause,
        )


if __name__ == "__main__":
    unittest.main()
