"""#207 product-owned selected trust and pure signed-transit laws."""
from dataclasses import FrozenInstanceError, replace
import base64
import hashlib
import importlib
import importlib.util
import json
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import control_plane_kit_core as core
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType,
)


CONFIG_MODULE = "control_plane_kit_servers_cpk_local_gateway.health_transit_configuration"
VERIFY_MODULE = "control_plane_kit_servers_cpk_local_gateway.health_transit_verification"
TOKEN_TYPE = "CPK-GATEWAY-NODE-HEALTH-READ-TRANSIT+JWT"
CLAIM = "gateway_node_health_read_transit"


def wire(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=")


class GatewayHealthTransitTests(unittest.TestCase):
    def setUp(self):
        self.private_a = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"207 synthetic A").digest())
        self.private_b = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"207 synthetic B").digest())
        self.key_a = self.public(self.private_a, "health-a")
        self.key_b = self.public(self.private_b, "health-b")
        roles = core.NodeControlGraphReferenceRole
        self.workspace = self.ref(roles.WORKSPACE, "workspace-a")
        self.gateway = self.ref(roles.NODE, "gateway-a")
        self.runtime = self.ref(roles.RUNTIME, "runtime-a")
        self.target = core.NodeControlTarget(self.workspace,
            self.ref(roles.GRAPH_REVISION, "graph-a"), self.ref(roles.NODE, "workload-a"),
            self.ref(roles.PROVIDER_SOCKET, "management"))
        self.declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(self.target.provider_socket_name, (),
                health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        self.request = core.NodeHealthReadRequest(self.target, self.runtime,
            core.NodeHealthReadKind.READINESS, self.declaration.identity(), "request-a")

    def api(self):
        # Existing Core/crypto fixtures are constructed before this target-red guard.
        self.assertIsNotNone(importlib.util.find_spec(CONFIG_MODULE),
            "#207 gateway health trust configuration is missing")
        self.assertIsNotNone(importlib.util.find_spec(VERIFY_MODULE),
            "#207 gateway health transit verifier is missing")
        return importlib.import_module(CONFIG_MODULE), importlib.import_module(VERIFY_MODULE)

    def ref(self, role, value):
        return core.NodeControlGraphReference(role, value)

    def public(self, private, key_id):
        return core.DelegationPublicKey(key_id, core.DelegationKeyAlgorithm.ED25519,
            private.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"))

    def config(self, api, **changes):
        return api.GatewayHealthTransitConfiguration(**(dict(workspace_id=self.workspace,
            gateway_node_id=self.gateway, runtime_id=self.runtime, issuer="parent-a",
            purpose=core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
            public_keys=(self.key_a,)) | changes))

    def artifact(self, api, **changes):
        return api.gateway_health_transit_configuration_artifact(self.config(api, **changes))

    def verifier(self, config_api, verifier_api, **changes):
        return verifier_api.gateway_health_transit_verifier_from_artifact(self.artifact(config_api, **changes))

    def grant(self, request=None, **changes):
        request = self.request if request is None else request
        return core.DelegatedGatewayNodeHealthReadTransitGrant(**(dict(
            profile=core.DelegatedGatewayNodeHealthReadTransitGrantProfile.V1,
            canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
            purpose=core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
            issuer="parent-a", key_id=self.key_a.key_id, attempt_id="attempt-a",
            gateway_node_id=self.gateway, target=request.target, runtime_id=request.runtime_id,
            kind=request.kind, declaration_identity=request.declaration_identity,
            request_id=request.request_id, request_digest=request.canonical_digest(),
            issued_at=100, not_before=110, expires_at=200, jti="transit-a") | changes))

    def payload(self, grant):
        return dict(iss=grant.issuer, aud=grant.audience, iat=grant.issued_at,
            nbf=grant.not_before, exp=grant.expires_at, jti=grant.jti,
            **{CLAIM: grant.descriptor()})

    def token(self, grant=None, *, private=None, header=None, payload=None,
              header_bytes=None, payload_bytes=None):
        grant = self.grant() if grant is None else grant
        header = dict(alg="EdDSA", typ=TOKEN_TYPE, kid=grant.key_id) if header is None else header
        payload = self.payload(grant) if payload is None else payload
        message = b64(wire(header) if header_bytes is None else header_bytes) + b"." + b64(
            wire(payload) if payload_bytes is None else payload_bytes)
        signature = (self.private_a if private is None else private).sign(message)
        return message + b"." + b64(signature)

    def verify(self, verifier, credential=None, request=None, **changes):
        return verifier.verify(self.token() if credential is None else credential,
            self.request if request is None else request, **(dict(expected_attempt_id="attempt-a",
                expected_target=self.target, expected_runtime_id=self.runtime,
                expected_declaration=self.declaration, expected_kind=core.NodeHealthReadKind.READINESS,
                now=150) | changes))

    def refused(self, error_type, action, message):
        with self.assertRaises(error_type) as caught:
            action()
        error = caught.exception
        self.assertTrue(str(error) == message, "refusal text is bounded")
        self.assertTrue(vars(error) == {}, "refusal has no candidate attributes")
        self.assertTrue(error.__cause__ is None, "refusal has no candidate cause")
        self.assertTrue(error.__context__ is None, "refusal has no candidate context")

    def bad_config(self, api, action):
        self.refused(api.GatewayHealthTransitConfigurationError, action,
            "gateway health transit configuration is invalid")

    def bad_token(self, api, action):
        self.refused(api.GatewayHealthTransitVerificationError, action,
            "gateway health transit credential was rejected")

    def test_configuration_roundtrip_derived_audience_and_immutable_key_order(self):
        config_api, _ = self.api()
        config = self.config(config_api, public_keys=(self.key_b, self.key_a))
        self.assertTrue(config.public_keys == (self.key_a, self.key_b), "keys sort by ID")
        self.assertEqual(config.audience, "gateway:workspace-a:gateway-a")
        artifact = config_api.gateway_health_transit_configuration_artifact(config)
        restored = config_api.decode_gateway_health_transit_configuration(artifact.content.encode())
        self.assertTrue(restored == config, "selected configuration roundtrips")
        self.assertEqual((artifact.artifact_id, artifact.target_path, artifact.media_type, artifact.file_mode),
            ("gateway-health-transit", "/etc/cpk/gateway/health-transit.json",
             ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY))
        self.assertTrue(ConfigurationArtifact.from_descriptor(artifact.descriptor()) == artifact,
            "artifact roundtrips through Core")
        with self.assertRaises(FrozenInstanceError):
            config.issuer = "other"
        self.assertTrue(all(value not in repr(config) for value in (
            "parent-a", "BEGIN PUBLIC KEY", "workspace-a")), "configuration repr is redacted")

    def test_configuration_requires_exact_family_roles_and_public_key_identity(self):
        api, _ = self.api()
        distinct_keys = tuple(self.public(Ed25519PrivateKey.from_private_bytes(
            hashlib.sha256(f"207 synthetic bounded key {index}".encode()).digest()),
            f"bounded-{index:02}") for index in range(17))
        maximum = self.config(api, public_keys=distinct_keys[:16])
        self.assertEqual(len(maximum.public_keys), 16)
        self.bad_config(api, lambda: self.config(api, public_keys=distinct_keys))
        duplicate_material = replace(self.key_a, key_id="other-id")
        malformed = core.DelegationPublicKey("malformed", core.DelegationKeyAlgorithm.ED25519,
            "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n")
        wrong_curve = core.DelegationPublicKey("wrong-curve", core.DelegationKeyAlgorithm.ED25519,
            ec.derive_private_key(1, ec.SECP256R1()).public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
        class DerivedKey(core.DelegationPublicKey):
            pass
        derived = DerivedKey(self.key_a.key_id, self.key_a.algorithm, self.key_a.public_key_pem)
        cases = [dict(public_keys=()), dict(public_keys=[self.key_a]),
            dict(public_keys=(self.key_a,) * 17), dict(public_keys=(self.key_a, self.key_a)),
            dict(public_keys=(self.key_a, duplicate_material)), dict(public_keys=(malformed,)),
            dict(public_keys=(wrong_curve,)),
            dict(public_keys=(derived,)), dict(issuer="bad\nissuer"), dict(issuer=""),
            dict(workspace_id=self.gateway), dict(gateway_node_id=self.runtime),
            dict(runtime_id=self.workspace), dict(purpose="gateway-node-health-read-transit")]
        cases += [dict(purpose=purpose) for purpose in core.DelegationKeyPurpose
                  if purpose is not core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT]
        for index, changes in enumerate(cases):
            with self.subTest(case=index):
                self.bad_config(api, lambda: self.config(api, **changes))

    def test_raw_configuration_is_closed_bounded_and_candidate_free(self):
        api, _ = self.api()
        document = json.loads(self.artifact(api).content)
        canonical = wire(document)
        maximum = canonical + b" " * (16384 - len(canonical))
        self.assertEqual(len(maximum), 16384)
        self.assertTrue(api.decode_gateway_health_transit_configuration(maximum) == self.config(api),
            "valid whitespace-padded configuration at the size cap is accepted")
        self.bad_config(api, lambda: api.decode_gateway_health_transit_configuration(maximum + b" "))
        cases = [b"", b"\xff", b" " * 16385, b"[" * 2000 + b"0" + b"]" * 2000,
            b'{"profile":NaN}', b'{"profile":Infinity}',
            b'{"profile":"duplicate",' + wire(document)[1:]]
        for key in document:
            cases.append(wire({name: value for name, value in document.items() if name != key}))
        cases += [wire(document | changes) for changes in (
            {"extra": True}, {"profile": "unknown"}, {"public_keys": None},
            {"purpose": "workload-node-health-read"}, {"issuer": True},
            {"runtime_id": ["nested"]}, {"public_keys": [dict(document["public_keys"][0], algorithm="rsa")]},
            {"public_keys": [dict(document["public_keys"][0], fingerprint_sha256="a" * 64)]})]
        private_pem = self.private_a.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        cases.append(wire(document | {"public_keys": [dict(document["public_keys"][0], public_key_pem=private_pem)]}))
        for index, raw in enumerate(cases):
            with self.subTest(case=index):
                self.bad_config(api, lambda: api.decode_gateway_health_transit_configuration(raw))
        self.bad_config(api, lambda: api.decode_gateway_health_transit_configuration(wire(document).decode()))

    def test_selected_artifact_bytes_determine_real_verifier_trust_and_overlap(self):
        config_api, verifier_api = self.api()
        artifact_a = self.artifact(config_api)
        artifact_b = replace(artifact_a, content=self.artifact(config_api, public_keys=(self.key_b,)).content)
        self.assertTrue(artifact_a.content_digest != artifact_b.content_digest, "changed bytes have a fresh valid digest")
        first = verifier_api.gateway_health_transit_verifier_from_artifact(artifact_a)
        second = verifier_api.gateway_health_transit_verifier_from_artifact(artifact_b)
        token_a = self.token()
        token_b = self.token(self.grant(key_id=self.key_b.key_id), private=self.private_b)
        self.assertTrue(self.verify(first, token_a) == self.request, "A is trusted by A")
        self.bad_token(verifier_api, lambda: self.verify(second, token_a))
        self.assertTrue(self.verify(second, token_b) == self.request, "B is trusted by decoded B")
        overlap = self.verifier(config_api, verifier_api, public_keys=(self.key_b, self.key_a))
        for credential in (token_a, token_b):
            self.assertTrue(self.verify(overlap, credential) == self.request, "overlap covers either key")
        provenance_only = replace(artifact_a, source_digest="b" * 64)
        self.assertTrue(self.verify(verifier_api.gateway_health_transit_verifier_from_artifact(provenance_only))
            == self.request, "source digest does not replace actual content semantics")
        self.assertTrue(all(value not in repr(first) for value in (
            token_a.decode(), "BEGIN PUBLIC KEY", "parent-a")), "verifier repr is redacted")

    def test_factory_requires_exact_receiver_slot_and_actual_configuration(self):
        config_api, verifier_api = self.api()
        artifact = self.artifact(config_api)
        candidates = [None, replace(artifact, artifact_id="other"),
            replace(artifact, target_path="/etc/cpk/other.json"),
            replace(artifact, media_type=ConfigurationMediaType.TEXT),
            replace(artifact, content="{}")]
        # The Core mode enum is closed; exercise another supported mode if present.
        candidates += [replace(artifact, file_mode=mode) for mode in ConfigurationFileMode
                       if mode is not ConfigurationFileMode.READ_ONLY]
        for index, candidate in enumerate(candidates):
            with self.subTest(case=index):
                self.bad_config(config_api,
                    lambda: verifier_api.gateway_health_transit_verifier_from_artifact(candidate))

    def test_real_signed_requests_preserve_both_kinds_and_repeat_without_replay_state(self):
        config_api, verifier_api = self.api()
        verifier = self.verifier(config_api, verifier_api)
        for kind in core.NodeHealthReadKind:
            request = replace(self.request, kind=kind)
            credential = self.token(self.grant(request))
            for _ in range(2):
                self.assertTrue(self.verify(verifier, credential, request, expected_kind=kind) is request,
                    "pure verifier returns the exact independently supplied request")

    def test_expected_attempt_target_runtime_declaration_and_action_are_independent(self):
        config_api, verifier_api = self.api()
        verifier = self.verifier(config_api, verifier_api)
        cases = [dict(expected_attempt_id="other-attempt"), dict(expected_attempt_id=True),
            dict(expected_runtime_id=replace(self.runtime, value="other-runtime")),
            dict(expected_kind=core.NodeHealthReadKind.LIVENESS),
            dict(expected_declaration=replace(self.declaration,
                surface=replace(self.declaration.surface, health_reads=(core.NodeHealthReadKind.LIVENESS,))))]
        cases += [dict(expected_target=replace(self.target,
            **{field: replace(getattr(self.target, field), value="other")}))
            for field in ("workspace_id", "graph_revision", "node_id", "provider_socket_name")]
        for index, changes in enumerate(cases):
            with self.subTest(case=index):
                self.bad_token(verifier_api, lambda: self.verify(verifier, **changes))
        self.bad_token(verifier_api, lambda: self.verify(verifier, request=replace(self.request, request_id="other-request")))
        self.bad_token(verifier_api, lambda: self.verify(verifier, request=object()))

    def test_configured_receiver_workspace_gateway_runtime_and_issuer_are_required(self):
        config_api, verifier_api = self.api()
        for field, value in (("workspace_id", replace(self.workspace, value="other-workspace")),
                             ("gateway_node_id", replace(self.gateway, value="other-gateway")),
                             ("runtime_id", replace(self.runtime, value="other-runtime")),
                             ("issuer", "other-parent")):
            with self.subTest(field=field):
                verifier = self.verifier(config_api, verifier_api, **{field: value})
                self.bad_token(verifier_api, lambda: self.verify(verifier))

    def test_exact_half_open_interval_has_no_probe_skew_or_implicit_clock(self):
        config_api, verifier_api = self.api()
        verifier = self.verifier(config_api, verifier_api)
        for now in (110, 199):
            self.assertTrue(self.verify(verifier, now=now) == self.request, "original interval accepted")
        for now in (109, 200, 201, True, 150.0, -1, 2**53):
            with self.subTest(now_type=type(now).__name__):
                self.bad_token(verifier_api, lambda: self.verify(verifier, now=now))

    def test_signature_selected_key_and_outer_inner_claims_are_congruent(self):
        config_api, verifier_api = self.api()
        verifier = self.verifier(config_api, verifier_api, public_keys=(self.key_a, self.key_b))
        grant = self.grant()
        cases = [self.token(private=self.private_b),
            self.token(header=dict(alg="EdDSA", typ=TOKEN_TYPE, kid="unknown")),
            self.token(private=self.private_b, header=dict(alg="EdDSA", typ=TOKEN_TYPE, kid=self.key_b.key_id))]
        for field, value in (("iss", "other-parent"), ("aud", "gateway:other:gateway-a"),
                             ("iat", 99), ("nbf", 109), ("exp", 201), ("jti", "other-jti")):
            cases.append(self.token(payload=self.payload(grant) | {field: value}))
        # True == 1 in Python: this specifically requires exact integer admission.
        early = self.grant(issued_at=1, not_before=1, expires_at=200)
        cases.append(self.token(early, payload=self.payload(early) | {"iat": True}))
        for field, value in (("purpose", "gateway-probe"), ("request_digest", "b" * 64),
                             ("key_id", self.key_b.key_id)):
            cases.append(self.token(payload=self.payload(grant) | {CLAIM: grant.descriptor() | {field: value}}))
        for index, credential in enumerate(cases):
            with self.subTest(case=index):
                self.bad_token(verifier_api, lambda: self.verify(verifier, credential))

    def test_signed_json_profiles_reject_duplicates_unknowns_and_deep_candidates(self):
        config_api, verifier_api = self.api()
        verifier = self.verifier(config_api, verifier_api)
        header = dict(alg="EdDSA", typ=TOKEN_TYPE, kid=self.key_a.key_id)
        payload = self.payload(self.grant())
        cases = [self.token(header=header | {"alg": "none"}),
            self.token(header=header | {"typ": "CPK-GATEWAY-PROBE+JWT"}),
            self.token(header=header | {"extra": True}), self.token(payload=payload | {"extra": True}),
            self.token(header_bytes=b'{"kid":"duplicate",' + wire(header)[1:]),
            self.token(payload_bytes=b'{"iss":"duplicate",' + wire(payload)[1:]),
            self.token(payload_bytes=wire(payload).replace(b'"purpose":', b'"purpose":"duplicate","purpose":', 1)),
            self.token(payload_bytes=b'{"iss":NaN}'),
            self.token(payload_bytes=b"[" * 2000 + b"0" + b"]" * 2000)]
        for field in header:
            cases.append(self.token(header={key: value for key, value in header.items() if key != field}))
        for field in payload:
            cases.append(self.token(payload={key: value for key, value in payload.items() if key != field}))
        for index, credential in enumerate(cases):
            with self.subTest(case=index):
                self.bad_token(verifier_api, lambda: self.verify(verifier, credential))

    def test_compact_envelope_and_signature_bounds_reject_without_disclosing_candidates(self):
        config_api, verifier_api = self.api()
        verifier = self.verifier(config_api, verifier_api)
        header = wire(dict(alg="EdDSA", typ=TOKEN_TYPE, kid=self.key_a.key_id))
        payload = wire(self.payload(self.grant()))
        # These remain valid JSON and are freshly signed over the padded bytes.
        # Unpadded base64url cannot have length1mod4: first over-cap is +2.
        maximum_header = header + b" " * (768 - len(header))
        maximum_payload = payload + b" " * (6144 - len(payload))
        at_cap = self.token(header_bytes=maximum_header, payload_bytes=maximum_payload)
        self.assertEqual(tuple(map(len, at_cap.split(b"."))), (1024, 8192, 86))
        self.assertTrue(self.verify(verifier, at_cap) == self.request,
            "valid freshly signed envelope at both reachable segment caps is accepted")
        for header_bytes, payload_bytes, lengths in (
            (maximum_header + b" ", maximum_payload, (1026, 8192, 86)),
            (maximum_header, maximum_payload + b" ", (1024, 8194, 86)),
        ):
            over_cap = self.token(header_bytes=header_bytes, payload_bytes=payload_bytes)
            self.assertEqual(tuple(map(len, over_cap.split(b"."))), lengths)
            self.assertLess(len(over_cap), 12288)
            self.bad_token(verifier_api, lambda: self.verify(verifier, over_cap))
        credential = self.token()
        parts = credential.split(b".")
        alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        noncanonical = parts[2][:-1] + bytes([alphabet[alphabet.index(parts[2][-1]) + 1]])
        candidates = [b"", b"\xff", b"a.b", credential + b".extra", credential.decode(),
            b".".join((parts[0] + b"=", parts[1], parts[2])),
            b".".join((parts[0], parts[1], noncanonical)),
            b".".join((parts[0], parts[1], b64(b"x" * 63))),
            b".".join((parts[0], parts[1], b64(b"x" * 65))),
            b"A" * 12289]  # early coarse cap; not an independent valid-segment boundary
        for index, limit in enumerate((1024, 8192, 86)):
            changed = list(parts)
            changed[index] = b"A" * (limit + 1)
            candidates.append(b".".join(changed))
        for index, value in enumerate(candidates):
            with self.subTest(case=index):
                self.bad_token(verifier_api, lambda: self.verify(verifier, value))
