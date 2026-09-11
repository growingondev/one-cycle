from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app as backend_app, create_app


class AdminApiContractTest(unittest.TestCase):

    def test_admin_route_contract(self):
        openapi_paths = (
            backend_app.openapi().get("paths", {})
        )

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
                "options",
                "head",
            }
        }

        expected_routes = {
            ("POST", "/api/admin/auth/login"),
            ("GET", "/api/admin/auth/me"),
            ("POST", "/api/admin/auth/logout"),

            ("GET", "/api/admin/announcements"),
            ("GET", "/api/admin/announcements/{announcement_id}"),
            ("POST", "/api/admin/announcements/collect"),
            (
                "POST",
                "/api/admin/announcements/"
                "{announcement_id}/recollect",
            ),

            ("GET", "/api/admin/documents"),
            ("GET", "/api/admin/documents/{document_id}"),
            (
                "GET",
                "/api/admin/documents/{document_id}/download",
            ),
            (
                "POST",
                "/api/admin/documents/{document_id}/reprocess",
            ),

            ("GET", "/api/admin/processing-runs"),

            ("GET", "/api/admin/errors"),
            ("GET", "/api/admin/errors/{error_id}"),
            (
                "PATCH",
                "/api/admin/errors/{error_id}/status",
            ),
            (
                "POST",
                "/api/admin/errors/{error_id}/retry",
            ),
        }

        for route in expected_routes:
            self.assertIn(route, routes)

        # MVP에서 사용하지 않는 임시 Frontend 계약은
        # 실제 Backend API가 아니다.
        self.assertNotIn(
            ("GET", "/api/admin/notices"),
            routes,
        )
        self.assertNotIn(
            (
                "DELETE",
                "/api/admin/announcements/{announcement_id}",
            ),
            routes,
        )
        self.assertNotIn(
            (
                "POST",
                "/api/admin/errors/{error_id}/notes",
            ),
            routes,
        )
        self.assertNotIn(
            ("GET", "/api/admin/announcements/export"),
            routes,
        )
        self.assertNotIn(
            ("GET", "/api/admin/documents/export"),
            routes,
        )
        self.assertNotIn(
            ("GET", "/api/admin/errors/export"),
            routes,
        )

    def test_admin_login_me_logout_cookie_flow(self):
        env = {
            "ADMIN_ID": "admin",
            "ADMIN_PASSWORD": "test-password",
            "ADMIN_JWT_SECRET": "test-secret-for-admin-contract",
            "ADMIN_JWT_EXPIRE_SECONDS": "3600",
            "ADMIN_COOKIE_NAME": "admin_access_token",
            "ADMIN_COOKIE_SECURE": "false",
            "ADMIN_COOKIE_SAMESITE": "lax",
        }

        with patch.dict(
            os.environ,
            env,
            clear=False,
        ):
            with TestClient(create_app()) as client:
                login_response = client.post(
                    "/api/admin/auth/login",
                    json={
                        "admin_id": "admin",
                        "password": "test-password",
                    },
                )

                self.assertEqual(
                    login_response.status_code,
                    200,
                )

                body = login_response.json()

                self.assertEqual(
                    body,
                    {
                        "authenticated": True,
                        "admin_id": "admin",
                        "role": "admin",
                    },
                )

                # Frontend가 token/access_token을
                # sessionStorage에 저장하는 계약이 아니다.
                self.assertNotIn("token", body)
                self.assertNotIn("access_token", body)

                set_cookie = login_response.headers.get(
                    "set-cookie",
                    "",
                )

                self.assertIn(
                    "admin_access_token=",
                    set_cookie,
                )
                self.assertIn(
                    "httponly",
                    set_cookie.lower(),
                )

                me_response = client.get(
                    "/api/admin/auth/me"
                )

                self.assertEqual(
                    me_response.status_code,
                    200,
                )
                self.assertEqual(
                    me_response.json()["admin_id"],
                    "admin",
                )

                logout_response = client.post(
                    "/api/admin/auth/logout"
                )

                self.assertEqual(
                    logout_response.status_code,
                    200,
                )
                self.assertEqual(
                    logout_response.json(),
                    {"success": True},
                )

                after_logout = client.get(
                    "/api/admin/auth/me"
                )

                self.assertEqual(
                    after_logout.status_code,
                    401,
                )

    def test_admin_login_rejects_invalid_credentials(self):
        env = {
            "ADMIN_ID": "admin",
            "ADMIN_PASSWORD": "test-password",
            "ADMIN_JWT_SECRET": "test-secret-for-admin-contract",
            "ADMIN_COOKIE_NAME": "admin_access_token",
            "ADMIN_COOKIE_SECURE": "false",
        }

        with patch.dict(
            os.environ,
            env,
            clear=False,
        ):
            with TestClient(create_app()) as client:
                response = client.post(
                    "/api/admin/auth/login",
                    json={
                        "admin_id": "admin",
                        "password": "wrong-password",
                    },
                )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_admin_api_requires_authentication(self):
        with TestClient(create_app()) as client:
            response = client.get(
                "/api/admin/announcements"
            )

        self.assertEqual(
            response.status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
