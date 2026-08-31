from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.app.main import app
from backend.app.schemas.glossary import (
    GlossaryAdminItem,
    GlossaryAdminListResponse,
    GlossaryCreateRequest,
    GlossaryPublicItem,
    GlossaryStatusUpdateRequest,
    GlossaryUpdateRequest,
)


class GlossaryContractTest(unittest.TestCase):

    def test_glossary_route_contract(self):
        openapi_paths = app.openapi().get("paths", {})

        routes = {
            (method.upper(), path)
            for path, operations in openapi_paths.items()
            for method in operations
            if method.lower()
            in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
            }
        }

        expected_routes = {
            ("GET", "/api/glossary"),
            ("GET", "/api/admin/glossary"),
            ("POST", "/api/admin/glossary"),
            (
                "PUT",
                "/api/admin/glossary/{glossary_id}",
            ),
            (
                "PATCH",
                "/api/admin/glossary/{glossary_id}/status",
            ),
            (
                "DELETE",
                "/api/admin/glossary/{glossary_id}",
            ),
        }

        for route in expected_routes:
            self.assertIn(route, routes)

    def test_public_schema_excludes_is_active(self):
        fields = set(GlossaryPublicItem.model_fields)

        self.assertEqual(
            fields,
            {
                "id",
                "term",
                "definition",
                "category",
            },
        )
        self.assertNotIn("is_active", fields)

    def test_admin_item_schema_includes_is_active(self):
        self.assertEqual(
            set(GlossaryAdminItem.model_fields),
            {
                "id",
                "term",
                "definition",
                "category",
                "is_active",
            },
        )

    def test_admin_list_response_contract(self):
        self.assertEqual(
            set(GlossaryAdminListResponse.model_fields),
            {
                "items",
                "page",
                "size",
                "total",
                "total_pages",
            },
        )

    def test_create_update_status_request_contract(self):
        self.assertEqual(
            set(GlossaryCreateRequest.model_fields),
            {
                "term",
                "definition",
                "category",
                "is_active",
            },
        )

        self.assertEqual(
            set(GlossaryUpdateRequest.model_fields),
            {
                "term",
                "definition",
                "category",
                "is_active",
            },
        )

        self.assertEqual(
            set(GlossaryStatusUpdateRequest.model_fields),
            {"is_active"},
        )

    def test_seed_contains_40_unique_active_terms(self):
        path = Path(
            "backend/app/seeds/glossary_seed.json"
        )

        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        self.assertEqual(len(data), 40)

        terms = [
            item["term"]
            for item in data
        ]

        self.assertEqual(
            len(set(terms)),
            40,
        )

        self.assertTrue(
            all(
                item["is_active"] is True
                for item in data
            )
        )

        self.assertTrue(
            all(
                set(item)
                == {
                    "term",
                    "definition",
                    "category",
                    "is_active",
                }
                for item in data
            )
        )

    def test_duplicate_term_is_database_unique(self):
        from backend.app.models.glossary import Glossary

        term_column = Glossary.__table__.c.term

        self.assertFalse(term_column.nullable)
        self.assertTrue(term_column.unique)


if __name__ == "__main__":
    unittest.main()
