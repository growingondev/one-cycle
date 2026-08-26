from __future__ import annotations

import unittest
from unittest.mock import ANY, patch

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_current_admin
from backend.app.db.session import get_db
from backend.app.main import create_app
from backend.app.services.glossary_service import (
    DuplicateGlossaryTermError,
)


PUBLIC_ITEM = {
    "id": 1,
    "term": "test-term",
    "definition": "test-definition",
    "category": "test-category",
    "is_active": True,
}

ADMIN_ITEM = {
    "id": 1,
    "term": "test-term",
    "definition": "test-definition",
    "category": "test-category",
    "is_active": True,
}


def _override_admin():
    return {
        "sub": "glossary-api-test",
        "role": "admin",
    }


class GlossaryApiTest(unittest.TestCase):

    def _app(self, *, authenticated: bool = True):
        application = create_app()

        # Service 함수를 patch하므로 실제 DB 연결은 하지 않는다.
        application.dependency_overrides[get_db] = (
            lambda: object()
        )

        if authenticated:
            application.dependency_overrides[
                get_current_admin
            ] = _override_admin

        return application

    def test_public_glossary_response_contract(self):
        application = self._app()

        with patch(
            "backend.app.api.routes.glossary."
            "list_public_glossary",
            return_value=[PUBLIC_ITEM],
        ):
            with TestClient(application) as client:
                response = client.get("/api/glossary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

        # Public 응답에서는 is_active가 노출되지 않는다.
        self.assertEqual(
            response.json()[0],
            {
                "id": 1,
                "term": "test-term",
                "definition": "test-definition",
                "category": "test-category",
            },
        )

    def test_admin_glossary_requires_authentication(self):
        application = self._app(
            authenticated=False,
        )

        with TestClient(application) as client:
            response = client.get(
                "/api/admin/glossary"
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "detail":
                    "\uad00\ub9ac\uc790 "
                    "\ub85c\uadf8\uc778\uc774 "
                    "\ud544\uc694\ud569\ub2c8\ub2e4."
            },
        )

    def test_admin_list_forwards_filters(self):
        application = self._app()

        service_result = {
            "items": [],
            "page": 2,
            "size": 5,
            "total": 0,
            "total_pages": 0,
        }

        with patch(
            "backend.app.api.routes.glossary."
            "list_admin_glossary",
            return_value=service_result,
        ) as mock_service:
            with TestClient(application) as client:
                response = client.get(
                    "/api/admin/glossary",
                    params={
                        "page": 2,
                        "size": 5,
                        "search":
                            "\uc8fc\ud0dd",
                        "category":
                            "\uccad\uc57d/\uc790\uaca9",
                        "is_active": "false",
                    },
                )

        self.assertEqual(response.status_code, 200)

        mock_service.assert_called_once_with(
            db=ANY,
            page=2,
            size=5,
            search="\uc8fc\ud0dd",
            category="\uccad\uc57d/\uc790\uaca9",
            is_active=False,
        )

    def test_create_returns_201_and_duplicate_returns_409(self):
        application = self._app()

        request_body = {
            "term": "new-term",
            "definition": "new-definition",
            "category": "new-category",
            "is_active": True,
        }

        with patch(
            "backend.app.api.routes.glossary."
            "create_glossary",
            return_value={
                "id": 10,
                **request_body,
            },
        ):
            with TestClient(application) as client:
                response = client.post(
                    "/api/admin/glossary",
                    json=request_body,
                )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["term"],
            "new-term",
        )

        with patch(
            "backend.app.api.routes.glossary."
            "create_glossary",
            side_effect=DuplicateGlossaryTermError(
                "new-term"
            ),
        ):
            with TestClient(application) as client:
                duplicate = client.post(
                    "/api/admin/glossary",
                    json=request_body,
                )

        self.assertEqual(
            duplicate.status_code,
            409,
        )
        self.assertEqual(
            duplicate.json()["detail"],
            "\uc774\ubbf8 "
            "\ub4f1\ub85d\ub41c "
            "\uc6a9\uc5b4\uc785\ub2c8\ub2e4.",
        )

    def test_update_returns_200_409_and_404(self):
        application = self._app()

        request_body = {
            "term": "updated-term",
            "definition": "updated-definition",
            "category": "updated-category",
            "is_active": True,
        }

        with patch(
            "backend.app.api.routes.glossary."
            "update_glossary",
            return_value={
                "id": 20,
                **request_body,
            },
        ):
            with TestClient(application) as client:
                response = client.put(
                    "/api/admin/glossary/20",
                    json=request_body,
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["term"],
            "updated-term",
        )

        with patch(
            "backend.app.api.routes.glossary."
            "update_glossary",
            side_effect=DuplicateGlossaryTermError(
                "updated-term"
            ),
        ):
            with TestClient(application) as client:
                duplicate = client.put(
                    "/api/admin/glossary/20",
                    json=request_body,
                )

        self.assertEqual(duplicate.status_code, 409)

        with patch(
            "backend.app.api.routes.glossary."
            "update_glossary",
            return_value=None,
        ):
            with TestClient(application) as client:
                missing = client.put(
                    "/api/admin/glossary/999",
                    json=request_body,
                )

        self.assertEqual(missing.status_code, 404)

    def test_status_patch_returns_200_and_404(self):
        application = self._app()

        with patch(
            "backend.app.api.routes.glossary."
            "update_glossary_status",
            return_value={
                **ADMIN_ITEM,
                "is_active": False,
            },
        ):
            with TestClient(application) as client:
                response = client.patch(
                    "/api/admin/glossary/1/status",
                    json={"is_active": False},
                )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.json()["is_active"]
        )

        with patch(
            "backend.app.api.routes.glossary."
            "update_glossary_status",
            return_value=None,
        ):
            with TestClient(application) as client:
                missing = client.patch(
                    "/api/admin/glossary/999/status",
                    json={"is_active": False},
                )

        self.assertEqual(missing.status_code, 404)

    def test_delete_returns_204_and_404(self):
        application = self._app()

        with patch(
            "backend.app.api.routes.glossary."
            "delete_glossary",
            return_value=True,
        ):
            with TestClient(application) as client:
                response = client.delete(
                    "/api/admin/glossary/1"
                )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

        with patch(
            "backend.app.api.routes.glossary."
            "delete_glossary",
            return_value=False,
        ):
            with TestClient(application) as client:
                missing = client.delete(
                    "/api/admin/glossary/999"
                )

        self.assertEqual(missing.status_code, 404)

    def test_request_validation_rejects_invalid_payloads(self):
        application = self._app()

        with TestClient(application) as client:
            empty_term = client.post(
                "/api/admin/glossary",
                json={
                    "term": "",
                    "definition": "definition",
                    "category": "category",
                    "is_active": True,
                },
            )

            invalid_status = client.patch(
                "/api/admin/glossary/1/status",
                json={
                    "is_active": "not-a-boolean",
                },
            )

        self.assertEqual(
            empty_term.status_code,
            422,
        )
        self.assertEqual(
            invalid_status.status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
