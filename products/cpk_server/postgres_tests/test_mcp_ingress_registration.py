"""Exact-host authority registration through the released SDK and the production service factory."""
from datetime import datetime
import io
import logging
import unittest

import httpx2
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.public_ingress import IngressAuthorityReference
from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders
from control_plane_kit_operations.ingress_authorities import (
    CloudflareZoneIngressAuthorityCodec, ingress_authority_registration_id_for,
)
from control_plane_kit_servers_cpk_server.operations_application import (
    OperationsApplicationFactory, OperationsEffectPorts, OperationsIdFactories,
)
from draft_catalogue_fixture import DraftCatalogueFixture, NOW, principal
from test_standard_mcp import StandardMcpFixture
import test_mcp_product_topology_authoring as transport_fixture


READ = "get_ingress_authority_detail"
REGISTER = "register_ingress_authority"
WORKSPACE = "workspace-a"
REF = "hello-ingress"
PATH = f"/workspaces/{WORKSPACE}/ingress-authorities"
PROTECTED = {
    "api_token_ref": "secret://fixture/private-token-coordinate",
    "generated_secret_provider_registration_id": "sprov-private-fixture",
    "generated_secret_reference_prefix": "secret://fixture/private-generated-prefix",
}
AUTHORITY = {"provider_kind": "cloudflare", "account_id": "fixture-account", "zone_id": "fixture-zone",
    "zone_name": "example.test", "allowed_hostname_pattern": "hello.example.test", **PROTECTED}
COORDS = {"workspace_id": WORKSPACE, "authority_ref": REF}
ARGS = {**COORDS, "authority": AUTHORITY, "admitted_at": NOW, "idempotency_key": "register-hello"}


class IngressRegistrationCases(DraftCatalogueFixture, StandardMcpFixture):
    async def asyncSetUp(self):
        await StandardMcpFixture.asyncSetUp(self)
        self.log = io.StringIO()
        handler = logging.StreamHandler(self.log)
        logger = logging.getLogger()
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)

        def unexpected_effect(*args, **kwargs):
            raise AssertionError("authority registration must not acquire an effect port")
        ports = OperationsEffectPorts(None, None, None, HealthReceiverDecoders(()),
            unexpected_effect, disabled_runtime_adapter=unexpected_effect)
        factory = OperationsApplicationFactory(self.unit_of_work, ports,
            OperationsIdFactories(*(unexpected_effect for _ in range(5))), clock=lambda: NOW)
        self.host.services.update(factory().services)
        self.who = principal(scopes=(PolicyScope.INGRESS_AUTHORITY_REGISTER,))
        authenticate = self.host.verifier.authenticate
        self.host.verifier.authenticate = lambda token: self.who if token == b"valid-token" else authenticate(token)

    async def result(self, client, name, args, status=None):
        result = await client.call_tool(name, args)
        for sentinel in (*PROTECTED.values(), "inline-private-canary"):
            self.assertNotIn(sentinel, str(result.structured_content))
            self.assertNotIn(sentinel, str(result.content))
            self.assertNotIn(sentinel, self.log.getvalue())
        if status is None:
            self.assertFalse(result.is_error, result.structured_content)
        else:
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["status"], status)
        return result.structured_content

    def registrations(self):
        return self.connection.execute("SELECT workspace_id, registration_id, admitted_by, admitted_at "
            "FROM cpk_ingress_authorities ORDER BY workspace_id, registration_id").fetchall()

    async def test_register_and_inspect_with_separate_grants(self):
        authority = CloudflareZoneIngressAuthorityCodec().decode(AUTHORITY)
        expected_id = ingress_authority_registration_id_for(WORKSPACE, IngressAuthorityReference(REF), authority)
        unauthorized = await self.http.post("/mcp", headers={"Authorization": "", "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": REGISTER, "arguments": ARGS}})
        self.assertEqual(unauthorized.status_code, 401)
        async with self.client(self.mode) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertTrue({REGISTER, READ}.issubset(tools), "missing ingress registration or detail tool")
            self.assertTrue(tools[READ].annotations.read_only_hint)
            self.assertFalse(tools[REGISTER].annotations.read_only_hint)
            for scope in (PolicyScope.INSTANCE_WORKSPACE_EDIT, PolicyScope.PLAN_EXECUTE, PolicyScope.INGRESS_AUTHORITY_READ):
                self.who = principal(scopes=(scope,))
                await self.result(client, REGISTER, ARGS, 403)
            await self.result(client, READ, COORDS, 404)
            await self.result(client, READ, {**COORDS, "workspace_id": "workspace-b"}, 403)
            self.who = principal(scopes=(PolicyScope.INGRESS_AUTHORITY_REGISTER,))
            await self.result(client, REGISTER, {**ARGS, "workspace_id":"workspace-b"}, 403)
            for change in ({"api_token": "inline-private-canary"}, {"api_token_ref":"inline-private-canary"},
                           {"allowed_hostname_pattern":"*.example.test"}, {"allowed_hostname_pattern":"bad.example.org"},
                           {"endpoint":"https://example.test"}):
                await self.result(client, REGISTER, {**ARGS, "authority":{**AUTHORITY, **change}}, 400)
            for extra in ({"actor_id":"someone-else"}, {"admitted_at":"not-a-time"}):
                await self.result(client, REGISTER, {**ARGS, **extra}, 400)
            await self.result(client, REGISTER, {**ARGS, "idempotency_key":"x"*65536}, 413)
            self.assertEqual(self.registrations(), [])
            receipt = await self.result(client, REGISTER, ARGS)
            self.assertEqual(receipt, {**COORDS, "registration_id":expected_id,
                "provider_kind":"cloudflare", "status":"active"})
            first = self.registrations()
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0][:3], (WORKSPACE, expected_id, "operator-a"))
            self.assertEqual(first[0][3], datetime.fromisoformat(NOW))
            await self.result(client, READ, COORDS, 403)
            later = {**ARGS, "admitted_at":"2026-12-01T00:00:00Z", "idempotency_key":"independent-duplicate"}
            duplicate = await self.http.post(PATH, json={k:v for k,v in later.items() if k!="workspace_id"})
            self.assertEqual(duplicate.status_code, 200)
            self.assertEqual({k:duplicate.json()[k] for k in receipt}, receipt)
            await self.result(client, REGISTER, {**later,
                "authority":{**AUTHORITY, "api_token_ref":"secret://fixture/other"}}, 400)
            self.assertEqual(self.registrations(), first)
            self.who = principal(scopes=(PolicyScope.INGRESS_AUTHORITY_READ,))
            await self.result(client, REGISTER, ARGS, 403)
        async with self.client(self.mode) as reader:
            detail = await self.result(reader, READ, COORDS)
            http = await self.http.get(PATH+"/"+REF)
            self.assertEqual(http.status_code, 200)
            self.assertEqual(detail, http.json())
            record = detail["ingress_authority"]
            self.assertEqual(record["registration_id"], expected_id)
            self.assertEqual(record["status"], "active")
            self.assertEqual(record["authority"], {**AUTHORITY, **dict.fromkeys(PROTECTED, "<redacted>")})
            with self.unit_of_work() as uow:
                uow.stores.ingress_authorities.revoke(WORKSPACE, IngressAuthorityReference(REF))
                uow.commit()
            self.assertEqual((await self.result(reader, READ, COORDS))["ingress_authority"]["status"], "revoked")

    async def test_lost_registration_reply_is_read_back_without_resubmission(self):
        authority = CloudflareZoneIngressAuthorityCodec().decode(AUTHORITY)
        expected = ingress_authority_registration_id_for(WORKSPACE, IngressAuthorityReference(REF), authority)
        different = ingress_authority_registration_id_for(WORKSPACE, IngressAuthorityReference(REF),
            CloudflareZoneIngressAuthorityCodec().decode({**AUTHORITY, "api_token_ref":"secret://fixture/other"}))
        dropped = transport_fixture.DropCompletedReply(self.app, REGISTER)
        caught = None
        try:
            async with httpx2.AsyncClient(transport=dropped, base_url="http://127.0.0.1:8080",
                    headers={"Authorization":"Bearer valid-token"}) as http:
                async with self.client(self.mode, http=http) as client:
                    await client.call_tool(REGISTER, ARGS)
        except* transport_fixture.FixtureReplyLost as error:
            caught = error
        self.assertIsNotNone(caught)
        self.assertEqual(dropped.sends, 1)
        self.who = principal(scopes=(PolicyScope.INGRESS_AUTHORITY_READ,))
        async with self.client(self.mode) as fresh:
            record = (await self.result(fresh, READ, COORDS))["ingress_authority"]
            self.assertEqual(record["registration_id"], expected)
            self.assertNotEqual(record["registration_id"], different)
            self.assertEqual(record["status"], "active")
            self.assertEqual(record["authority"]["allowed_hostname_pattern"], "hello.example.test")
        self.assertEqual(len(self.registrations()), 1)


class AutoIngressTests(IngressRegistrationCases, unittest.IsolatedAsyncioTestCase):
    mode = "auto"


class LegacyIngressTests(IngressRegistrationCases, unittest.IsolatedAsyncioTestCase):
    mode = "legacy"
