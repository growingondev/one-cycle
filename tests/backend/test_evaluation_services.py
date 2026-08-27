import unittest
from unittest.mock import MagicMock, patch

from backend.app.services import evaluation_pipeline_service
from backend.app.services import evaluation_service


class EvaluationServiceTest(unittest.TestCase):

    @patch(
        "backend.app.services.evaluation_service."
        "persist_collection_result"
    )
    def test_registration_rejects_production_database(
        self,
        mock_persist,
    ):
        with patch.object(
            evaluation_service.settings,
            "postgres_db",
            "one_cycle",
        ):
            with self.assertRaises(RuntimeError):
                evaluation_service.register_evaluation_dataset(
                    dataset_id="test",
                    documents=[],
                )

        mock_persist.assert_not_called()


class EvaluationPipelineServiceTest(unittest.TestCase):

    def test_pipeline_rejects_production_database(self):
        with patch.object(
            evaluation_pipeline_service.settings,
            "postgres_db",
            "one_cycle",
        ):
            with self.assertRaises(RuntimeError):
                evaluation_pipeline_service._assert_evaluation_database()

    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "SessionLocal"
    )
    def test_pipeline_rejects_actual_database_mismatch(
        self,
        mock_session_local,
    ):
        db = (
            mock_session_local.return_value
            .__enter__.return_value
        )

        execute_result = MagicMock()
        execute_result.scalar_one.return_value = "one_cycle"
        db.execute.return_value = execute_result

        with patch.object(
            evaluation_pipeline_service.settings,
            "postgres_db",
            "one_cycle_evaluation_tmp",
        ):
            with self.assertRaises(RuntimeError):
                evaluation_pipeline_service._assert_evaluation_database()

    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "publish_collection_run"
    )
    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "process_document_ids"
    )
    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "_get_collection_document_ids"
    )
    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "_assert_evaluation_database"
    )
    def test_processing_failure_does_not_publish(
        self,
        mock_assert_db,
        mock_get_document_ids,
        mock_process,
        mock_publish,
    ):
        mock_get_document_ids.return_value = [10]

        mock_process.return_value = {
            "requested_count": 1,
            "success_count": 0,
            "failed_count": 1,
            "error_ids": [99],
            "results": [],
        }

        with self.assertRaises(RuntimeError):
            evaluation_pipeline_service.\
                process_and_publish_evaluation_collection(
                    collection_run_id=1
                )

        mock_assert_db.assert_called_once()
        mock_process.assert_called_once_with([10])
        mock_publish.assert_not_called()

    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "publish_collection_run"
    )
    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "_get_document_result"
    )
    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "process_document_ids"
    )
    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "_get_collection_document_ids"
    )
    @patch(
        "backend.app.services.evaluation_pipeline_service."
        "_assert_evaluation_database"
    )
    def test_successful_processing_publishes_collection(
        self,
        mock_assert_db,
        mock_get_document_ids,
        mock_process,
        mock_get_document_result,
        mock_publish,
    ):
        mock_get_document_ids.return_value = [10]

        mock_process.return_value = {
            "requested_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "error_ids": [],
            "results": [],
        }

        mock_get_document_result.return_value = {
            "evaluation_document_id": "DOC_TEST_001",
            "announcement_id": 20,
            "document_id": 10,
            "processing_run_id": 30,
            "chunk_set_id": 40,
            "chunk_count": 207,
            "embedding_count": 207,
            "embedding_model_name": "BAAI/bge-m3",
        }

        mock_publish.return_value = {
            "status": "published",
            "active_collection_run_id": 1,
        }

        result = (
            evaluation_pipeline_service.
            process_and_publish_evaluation_collection(
                collection_run_id=1
            )
        )

        mock_process.assert_called_once_with([10])
        mock_publish.assert_called_once_with(1)

        self.assertEqual(
            result["collection_run_id"],
            1,
        )
        self.assertEqual(
            result["processing"]["failed_count"],
            0,
        )
        self.assertEqual(
            result["documents"][0]["chunk_count"],
            207,
        )
        self.assertEqual(
            result["documents"][0]["embedding_count"],
            207,
        )
        self.assertEqual(
            result["publish"]["status"],
            "published",
        )


if __name__ == "__main__":
    unittest.main()
