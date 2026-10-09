import base64
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

from azure.storage.blob import UserDelegationKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from citation_file_handler import CitationFilesHandler


ROOT = Path(__file__).resolve().parents[3]


class DeploymentAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.site = (ROOT / "infra/host/appservices.bicep").read_text()
        self.main = (ROOT / "infra/main.bicep").read_text()
        self.parameters = (ROOT / "infra/main.parameters.json").read_text()
        self.app = (ROOT / "src/backend/app.py").read_text()

    def test_anonymous_requests_to_all_routes_require_sign_in(self):
        self.assertIn("name: 'authsettingsV2'", self.site)
        self.assertRegex(self.site, r"platform:\s*\{\s*enabled: true")
        self.assertRegex(self.site, r"globalValidation:\s*\{\s*requireAuthentication: true")
        self.assertIn("unauthenticatedClientAction: 'RedirectToLoginPage'", self.site)
        self.assertNotIn("excludedPaths:", self.site)
        for route in ("/chat", "/list_indexes", "/get_citation_doc"):
            self.assertIn(f'"{route}"', self.app)
        self.assertIn('app.router.add_static("/",', self.app)

    def test_invalid_identity_cannot_select_another_provider_or_tenant(self):
        self.assertRegex(self.site, r"azureActiveDirectory:\s*\{\s*enabled: true")
        self.assertIn("'${environment().authentication.loginEndpoint}${authTenantId}/v2.0'", self.site)
        self.assertIn("authTenantId: subscription().tenantId", self.main)
        self.assertIn("clientId: authClientId", self.site)
        self.assertRegex(self.site, r"allowedAudiences:\s*\[\s*authClientId\s*\]")
        self.assertIn("clientSecretSettingName: 'MICROSOFT_PROVIDER_AUTHENTICATION_SECRET'", self.site)
        self.assertIn("redirectToProvider: 'azureactivedirectory'", self.site)
        self.assertNotIn("AllowAnonymous", self.site)
        for source in (ROOT / "src/backend").glob("*.py"):
            self.assertNotIn("X-MS-CLIENT-PRINCIPAL", source.read_text())
        self.assertIn('"${AZURE_AUTH_CLIENT_ID}"', self.parameters)
        self.assertIn('"${AZURE_AUTH_CLIENT_SECRET}"', self.parameters)
        self.assertIn("@secure()", self.main)
        self.assertIn("httpSettings: {\n      requireHttps: true", self.site)
        self.assertIn("convention: 'NoProxy'", self.site)
        self.assertIn("webSocketsEnabled: false", self.site)

    def test_local_debug_cannot_bind_publicly_without_platform(self):
        self.assertIn('host not in ("localhost", "127.0.0.1", "::1")', self.app)
        self.assertIn('not os.environ.get("WEBSITE_INSTANCE_ID")', self.app)


class CitationSasTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        now = datetime.now(timezone.utc)
        key = UserDelegationKey()
        key.signed_oid = "00000000-0000-0000-0000-000000000001"
        key.signed_tid = "00000000-0000-0000-0000-000000000002"
        key.signed_start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        key.signed_expiry = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        key.signed_service = "b"
        key.signed_version = "2023-11-03"
        key.value = base64.b64encode(b"offline-test-key").decode()
        self.blob_service = SimpleNamespace(get_user_delegation_key=AsyncMock(return_value=key))
        self.container = SimpleNamespace(
            container_name="documents",
            get_blob_client=lambda name: SimpleNamespace(
                account_name="offline",
                url=f"https://offline.blob.core.windows.net/documents/{name}",
            ),
        )
        self.handler = CitationFilesHandler(self.blob_service, self.container)

    async def test_document_url_is_read_only_and_expires_within_five_minutes(self):
        before = datetime.now(timezone.utc)
        url = await self.handler._get_file_url("example.pdf")
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["sp"], ["r"])
        self.assertEqual(query["sr"], ["b"])
        expiry = datetime.fromisoformat(query["se"][0].replace("Z", "+00:00"))
        self.assertLessEqual(expiry, before + timedelta(minutes=5, seconds=1))
        self.assertGreater(expiry, before)
        self.blob_service.get_user_delegation_key.assert_awaited_once()

    async def test_valid_document_request_returns_signed_url(self):
        request = SimpleNamespace(json=AsyncMock(return_value={"fileName": "example.pdf"}))
        response = await self.handler.handle(request)
        self.assertEqual(response.status, 200)
        self.assertIn(b"https://offline.blob.core.windows.net/documents/example.pdf?", response.body)

    async def test_invalid_document_request_never_requests_a_delegation_key(self):
        from aiohttp import web

        for payload in ({}, {"fileName": ""}, {"fileName": 42}, []):
            with self.subTest(payload=payload):
                request = SimpleNamespace(json=AsyncMock(return_value=payload))
                with self.assertRaises(web.HTTPBadRequest):
                    await self.handler.handle(request)
        self.blob_service.get_user_delegation_key.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
