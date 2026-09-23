"""#221 owner composition laws; no live/provider/transaction-isolation claims."""
import importlib
import importlib.util
import json
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

from gateway_diagnostic_fixtures import encode, packet_world

MODULE = "control_plane_kit_servers_cpk_server.gateway_self_health_diagnostic"


class GatewayDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.addCleanup(self.clear_modules)
        self.world = packet_world()  # Real selected artifacts and Core grants before missing-interface check.
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "#221 diagnostic adapter is missing")
        self.api = importlib.import_module(MODULE)

    @staticmethod
    def clear_modules():
        for name in tuple(sys.modules):
            if name.startswith(("control_plane_kit_servers_cpk_server", "control_plane_kit_servers_cpk_local_gateway")):
                sys.modules.pop(name, None)

    def prepare(self, packet=None, artifacts=None):
        return self.api.prepare_packet(self.world.raw if packet is None else encode(packet),
            self.world.artifacts if artifacts is None else artifacts)

    def test_offline_plan_binds_real_self_selection_without_effects(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("offline network")):
            selected = self.prepare()
            result = selected.plan()
        self.assertEqual(result["status"], "offline-plan")
        self.assertEqual(result["authorization_writes"], 2)
        self.assertEqual(selected.context.request, self.world.request)
        self.assertEqual(selected.destination.target_id, self.world.value.binding.target_id)
        rendered = json.dumps(result)
        for forbidden in ("private-origin-canary", "secret://", "public_key_pem", "transit_grant"):
            self.assertNotIn(forbidden, rendered)

    def test_closed_bounded_packet_rejects_authority_claims_duplicates_and_oversize(self):
        for field in ("actor", "scopes", "approved", "database_url", "credential_file", "resolution_grants"):
            with self.subTest(field=field), self.assertRaises(self.api.DiagnosticInputError):
                self.prepare({**self.world.packet,field:"forged"})
        for raw in (b"{"+b'"profile":1,"profile":2}', b" "*65537):
            with self.assertRaises(self.api.DiagnosticInputError):
                self.api.prepare_packet(raw,self.world.artifacts)

    def test_selected_artifact_alias_request_and_window_mismatches_refuse(self):
        variants = [{**self.world.packet,"target_id":"other-alias"},
                    {**self.world.packet,"attempt_id":"other-attempt"}]
        wrong = dict(self.world.packet)
        wrong["request"] = replace(self.world.request,kind=type(self.world.request.kind).LIVENESS).descriptor()
        variants.append(wrong)
        for packet in variants:
            with self.assertRaises(self.api.DiagnosticInputError): self.prepare(packet)
        artifacts = dict(self.world.artifacts,control=b"{}")
        with self.assertRaises(self.api.DiagnosticInputError): self.prepare(artifacts=artifacts)

    def test_stable_correlations_depend_only_on_workspace_attempt_and_family(self):
        a = self.prepare()
        changed = {**self.world.packet,"resource_plan":"another-plan"}
        b = self.prepare(changed)
        self.assertEqual(a.correlations,b.correlations)
        self.assertEqual(len(set(a.correlations)),2)
        self.assertNotEqual(a.packet_digest,b.packet_digest)

    async def test_authentication_and_approval_refuse_before_opening_transaction(self):
        selected = self.prepare()
        authority = self.api.DiagnosticAuthority(verifier=None,credential=b"invalid",
            approval_reader=lambda: {},workspace_id="workspace-a",database_identity="existing-db",
            unit_of_work=lambda: self.fail("opened transaction"),resolver=None)
        result = await self.api.run_diagnostic(selected,authority,clock=lambda:150)
        self.assertEqual(result["status"],"approval-authentication-denied")

    def test_runner_has_plan_run_entrypoint_without_provisioning_options(self):
        from pathlib import Path
        script = Path(__file__).resolve().parents[3]/"scripts/gateway_self_health_diagnostic.py"
        self.assertTrue(script.is_file(), "diagnostic CLI is missing")
        # Runtime behavior and private bootstrap read laws are exercised after module discovery.
        self.assertTrue(callable(self.api.main))

    def test_offline_cli_reads_only_public_inputs_and_emits_bounded_plan(self):
        import contextlib
        import io
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"packet.json").write_bytes(self.world.raw)
            for name,raw in self.world.artifacts.items(): (root/(name+".json")).write_bytes(raw)
            output=io.StringIO()
            with patch.object(self.api,"load_authority",side_effect=AssertionError("private bootstrap read")) as loader, \
                    patch("socket.getaddrinfo",side_effect=AssertionError("offline network")), contextlib.redirect_stdout(output):
                code=self.api.main(["plan","--packet",str(root/"packet.json"),"--artifacts",str(root)])
            self.assertEqual(code,0)
            loader.assert_not_called()
            self.assertLessEqual(len(output.getvalue()),4096)
            self.assertEqual(json.loads(output.getvalue())["status"],"offline-plan")

    async def exercise(self, *, existing=False, exit_error=False, fail_second=False, clock=None, signer_error=False, configure=None):
        from gateway_diagnostic_fixtures import recording_authority
        selected = self.prepare()
        state = recording_authority(self.api,selected,self.world,existing=existing,exit_error=exit_error,fail_second=fail_second)
        if configure is not None: configure(state)
        signed=object()
        def sign(context,**kwargs):
            self.assertIn(("exit",None),state.events)
            state.events.append(("sign",))
            self.assertEqual(len(state.added),2)
            for key in (kwargs["transit_key"],kwargs["workload_key"]):
                self.assertTrue(key.resolution_grant.authorization_id.startswith("suse_"))
                self.assertEqual(key.resolution_grant.operation_id,"diagnostic-attempt")
            if signer_error: raise ValueError("private-signing-canary")
            self.assertEqual(context,selected.context)
            self.assertEqual(kwargs["transit_grant"],selected.transit_grant)
            self.assertEqual(kwargs["workload_grant"],selected.workload_grant)
            return signed
        async def dispatch(*args,**kwargs):
            state.events.append(("dispatch",))
            self.assertEqual(args,(selected.context,signed,selected.destination))
            self.assertEqual(kwargs,{"transit_grant":selected.transit_grant,"workload_grant":selected.workload_grant})
            from control_plane_kit_interpreters.probes.health_transport import GatewayHealthTransportResult,GatewayHealthTransportCode
            return GatewayHealthTransportResult(GatewayHealthTransportCode.TIMED_OUT)
        with patch.object(self.api,"Ed25519HealthCredentialPairSigner") as signer, patch.object(self.api,"SignedGatewayHealthClient") as client:
            signer.return_value.sign.side_effect=sign
            client.return_value.dispatch.side_effect=dispatch
            result=await self.api.run_diagnostic(selected,state.authority,clock=clock or (lambda:150))
            if client.called:
                self.assertEqual(set(client.call_args.kwargs),{"clock"})
        return result,state

    async def test_real_authorization_projection_precedes_one_sign_and_dispatch_after_exit(self):
        result,state=await self.exercise()
        self.assertEqual(result["status"],"timed-out")
        self.assertEqual([event[0] for event in state.events].count("sign"),1)
        self.assertEqual([event[0] for event in state.events].count("dispatch"),1)
        self.assertEqual(state.events[1:3],[("lock",key) for key in sorted(self.prepare().correlations)])
        self.assertEqual(len(set(value.authorization_id for value in state.added)),2)

    async def test_existing_either_correlation_and_second_authorization_error_never_sign(self):
        for arguments,code in ((dict(existing=True),"prior-attempt-refused"),(dict(fail_second=True),"admission-refused")):
            result,state=await self.exercise(**arguments)
            self.assertEqual(result["status"],code)
            self.assertNotIn(("commit-request",),state.events)
            self.assertNotIn(("sign",),state.events)
            self.assertNotIn(("dispatch",),state.events)
            self.assertNotIn("private-canary",json.dumps(result))

    async def test_commit_exit_ambiguity_never_reaches_signer(self):
        result,state=await self.exercise(exit_error=True)
        self.assertEqual(result["status"],"commit-uncertain")
        self.assertIn(("commit-request",),state.events)
        self.assertNotIn(("sign",),state.events)
        self.assertNotIn("database-private-canary",json.dumps(result))

    async def test_postcommit_expiry_and_signer_failure_preserve_authorizations_without_health_send(self):
        result,state=await self.exercise(signer_error=True)
        self.assertEqual(result["status"],"authorized-not-dispatched")
        self.assertEqual(len(result["authorization_ids"]),2)
        self.assertNotIn(("dispatch",),state.events)
        current=[150]
        def configure(state):
            state.hooks.on_exit=lambda:current.__setitem__(0,211)
        result,state=await self.exercise(clock=lambda:current[0],configure=configure)
        self.assertEqual(result["status"],"authorized-not-dispatched")
        self.assertNotIn(("sign",),state.events)

    async def test_real_verifier_policy_and_independent_approval_fail_closed(self):
        from control_plane_kit_core.identity import PrincipalKind,WorkspaceGrant
        original=self.world.principal
        principals=(replace(original,identity=replace(original.identity,kind=PrincipalKind.WORKER)),
            replace(original,workspace_grants=(WorkspaceGrant("workspace-a",()),)),
            replace(original,workspace_grants=(WorkspaceGrant("foreign",original.workspace_grants[0].scopes),)))
        for principal in principals:
            self.world.principal=principal
            result,state=await self.exercise()
            self.assertEqual(result["status"],"approval-authentication-denied")
            self.assertEqual(state.events,[])
        self.world.principal=original
        for field,value in (("issuer","other"),("subject","other"),("packet_digest","f"*64),
                ("attempt_id","other"),("database_identity","other"),("workspace_id","other"),
                ("expires_at",149),("expires_at",190)):
            result,state=await self.exercise(configure=lambda state:state.approval.__setitem__(field,value))
            self.assertEqual(result["status"],"approval-authentication-denied")
            self.assertEqual(state.events,[])

    async def test_each_existing_family_refuses_only_after_both_stable_locks(self):
        selected=self.prepare()
        for correlation in selected.correlations:
            result,state=await self.exercise(existing={correlation})
            self.assertEqual(result["status"],"prior-attempt-refused")
            self.assertEqual(state.events[1:3],[("lock",key) for key in sorted(selected.correlations)])
            self.assertEqual(state.added,[])
            self.assertNotIn(("sign",),state.events)

    async def test_changed_current_key_and_custody_routing_refuse_before_commit(self):
        from control_plane_kit_core.secrets import SecretReference,SecretProviderEndpointReference
        mutations=(
            lambda s:s.keys.__setitem__(0,replace(s.keys[0],registration_id="other")),
            lambda s:s.keys.__setitem__(0,replace(s.keys[0],issuer="other")),
            lambda s:s.keys.__setitem__(0,replace(s.keys[0],public_key=s.keys[1].public_key)),
            lambda s:s.keys.__setitem__(0,replace(s.keys[0],private_key_reference=SecretReference("secret://provider-a/other"))),
            lambda s:s.providers.__setitem__(0,replace(s.providers[0],endpoint_reference=SecretProviderEndpointReference("other"))),
            lambda s:s.providers.__setitem__(0,replace(s.providers[0],credential_reference=SecretReference("secret://bootstrap/other"))),
            lambda s:s.references.__setitem__(0,replace(s.references[0],registration_id="other")),
        )
        for change in mutations:
            result,state=await self.exercise(configure=change)
            self.assertEqual(result["status"],"admission-refused")
            self.assertNotIn(("commit-request",),state.events)
            self.assertNotIn(("sign",),state.events)

    def test_correlations_do_not_change_with_valid_window_or_key_selection(self):
        packet={**self.world.packet,"keys":[dict(item) for item in self.world.packet["keys"]]}
        packet["keys"][0]["registration_id"]="other-registration"
        for name,grant in (("transit_grant",self.world.transit),("workload_grant",self.world.workload)):
            packet[name]=replace(grant,issued_at=110,not_before=111,expires_at=210).descriptor()
        self.assertEqual(self.prepare(packet).correlations,self.prepare().correlations)

    async def test_postexit_approval_withdrawal_and_cancellation_do_not_sign(self):
        import asyncio
        def withdraw(state): state.hooks.on_exit=lambda:state.approval.clear()
        result,state=await self.exercise(configure=withdraw)
        self.assertEqual(result["status"],"authorized-not-dispatched")
        self.assertEqual(len(result["authorization_ids"]),2)
        self.assertNotIn(("sign",),state.events)
        observed=[]
        def cancel(state):
            observed.append(state)
            def cancelled(): raise asyncio.CancelledError()
            state.hooks.on_exit=cancelled
        with self.assertRaises(asyncio.CancelledError): await self.exercise(configure=cancel)
        self.assertNotIn(("sign",),observed[0].events)
