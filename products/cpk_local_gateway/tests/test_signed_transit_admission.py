from __future__ import annotations

import ast
import base64
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import rfc8785

import control_plane_kit_servers_cpk_local_gateway as gateway_root
from control_plane_kit_core.delegation_keys import (
    DelegationKeyAlgorithm,
    DelegationKeyPurpose,
    DelegationPublicKey,
)
from control_plane_kit_core.gateway_delegation import (
    DelegatedGatewayProbeGrant,
    GatewayProbeCommandKind,
    GatewayProbeRequest,
)
from control_plane_kit_core.node_control import (
    ControlPlaneCommandCodec,
    ControlPlaneTransitionPrecondition,
    DelegatedWorkloadNodeControlGrant,
    NodeControlCanonicalization,
    NodeControlCommandRequest,
    NodeControlCommandRequestCodec,
    NodeControlGraphReference,
    NodeControlGraphReferenceRole,
    NodeControlOperation,
    NodeControlPayload,
    NodeControlTarget,
    ScalarControlState,
    WeightedRoutingControlState,
)
from control_plane_kit_core.node_control_surface_reads import (
    DelegatedWorkloadNodeControlSurfaceReadGrant,
    DelegatedWorkloadNodeControlSurfaceReadGrantProfile,
    NodeControlSurfaceReadKind,
    NodeControlSurfaceReadRequest,
    WorkloadNodeControlSurfaceDeclarationIdentity,
)
from control_plane_kit_core.node_control_transit import (
    DelegatedGatewayNodeControlTransitGrant,
    DelegatedGatewayNodeControlTransitGrantCodec,
    DelegatedGatewayNodeControlTransitGrantProfile,
)
from control_plane_kit_core.runtime_effects import GatewayTargetId


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_local_gateway" / "src"
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "gateway_node_control_transit_admission_v1.json"
)
MODULE_NAME = "control_plane_kit_servers_cpk_local_gateway.transit_admission"
TOKEN_TYPE = "CPK-GATEWAY-NODE-CONTROL-TRANSIT+JWT"
MAX_CREDENTIAL_BYTES = 5_167
MAX_HEADER_SEGMENT_BYTES = 263
MAX_PAYLOAD_SEGMENT_BYTES = 4_816
MAX_SIGNATURE_SEGMENT_BYTES = 86
MAX_STRUCTURAL_JSON_MEMBERS = 64
SEED = bytes(range(32))


def _reference(
    role: NodeControlGraphReferenceRole,
    value: str,
) -> NodeControlGraphReference:
    return NodeControlGraphReference(role, value)


def _base64url(value: bytes) -> bytes:
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def _decode_base64url(value: bytes) -> bytes:
    return base64.urlsafe_b64decode(value + b"=" * (-len(value) % 4))


def _signed_credential(
    header: dict[str, object],
    payload: dict[str, object],
    *,
    seed: bytes = SEED,
) -> bytes:
    protected = _base64url(rfc8785.dumps(header))
    claims = _base64url(rfc8785.dumps(payload))
    signing_input = protected + b"." + claims
    signature = Ed25519PrivateKey.from_private_bytes(seed).sign(signing_input)
    return signing_input + b"." + _base64url(signature)


def _public_key(seed: bytes = SEED, *, key_id: str) -> DelegationPublicKey:
    pem = (
        Ed25519PrivateKey.from_private_bytes(seed)
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return DelegationPublicKey(key_id, DelegationKeyAlgorithm.ED25519, pem)


class SignedTransitAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self._validate_independent_fixture()

    def tearDown(self) -> None:
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == MODULE_NAME:
                sys.modules.pop(name, None)

    def _validate_independent_fixture(self) -> None:
        credential = self.fixture["credential_ascii"].encode("ascii")
        protected, claims, signature = credential.split(b".")
        self.assertEqual(
            rfc8785.dumps(self.fixture["header"]),
            _decode_base64url(protected),
        )
        self.assertEqual(
            rfc8785.dumps(self.fixture["payload"]),
            _decode_base64url(claims),
        )
        self.assertEqual(
            rfc8785.dumps(self.fixture["request"]),
            self.fixture["request_canonical_utf8"].encode("utf-8"),
        )
        public = serialization.load_pem_public_key(
            self.fixture["public_key_pem"].encode("ascii")
        )
        public.verify(_decode_base64url(signature), protected + b"." + claims)
        request = NodeControlCommandRequestCodec().decode_canonical_bytes(
            self.fixture["request_canonical_utf8"].encode("utf-8")
        )
        grant = DelegatedGatewayNodeControlTransitGrantCodec().decode(
            self.fixture["payload"]["gateway_node_control_transit"]
        )
        self.assertEqual(grant.request_digest, request.canonical_digest())
        self.assertEqual(
            (
                self.fixture["payload"]["iss"],
                self.fixture["payload"]["aud"],
                self.fixture["payload"]["iat"],
                self.fixture["payload"]["nbf"],
                self.fixture["payload"]["exp"],
                self.fixture["payload"]["jti"],
            ),
            (
                grant.issuer,
                grant.audience,
                grant.issued_at,
                grant.not_before,
                grant.expires_at,
                grant.jti,
            ),
        )

    def module(self):
        self.assertIsNotNone(
            importlib.util.find_spec(MODULE_NAME),
            "signed gateway transit admission is not implemented",
        )
        return importlib.import_module(MODULE_NAME)

    def contract(self, name: str):
        value = getattr(self.module(), name, None)
        self.assertIsNotNone(value, f"{name} is not implemented")
        return value

    def verifier(
        self,
        *,
        issuer: str = "cpk-server",
        workspace_id: str = "workspace-1",
        gateway_node_id: str = "gateway-1",
        public_keys: tuple[DelegationPublicKey, ...] | None = None,
    ):
        verifier_type = self.contract("Ed25519GatewayNodeControlTransitVerifier")
        return verifier_type(
            issuer=issuer,
            workspace_id=_reference(
                NodeControlGraphReferenceRole.WORKSPACE,
                workspace_id,
            ),
            gateway_node_id=_reference(
                NodeControlGraphReferenceRole.NODE,
                gateway_node_id,
            ),
            public_keys=public_keys
            or (_public_key(key_id="gateway-transit-key-1"),),
        )

    def fixture_request_bytes(self) -> bytes:
        return self.fixture["request_canonical_utf8"].encode("utf-8")

    def fixture_credential(self) -> bytes:
        return self.fixture["credential_ascii"].encode("ascii")

    def assert_rejected(self, callback, *canaries: str) -> None:
        error_type = self.contract("GatewayNodeControlTransitAdmissionError")
        with self.assertRaises(error_type) as caught:
            callback()
        rendered = str(caught.exception)
        self.assertLessEqual(len(rendered), 128)
        for canary in canaries:
            self.assertNotIn(canary, rendered)
            self.assertNotIn(canary, repr(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def verify_fixture(self, **changes: object):
        values = {
            "credential": self.fixture_credential(),
            "request_bytes": self.fixture_request_bytes(),
            "expected_attempt_id": "attempt-1",
            "effective_now": self.fixture["effective_now"],
        }
        values.update(changes)
        return self.verifier().verify(**values)

    def test_profile_public_types_exports_and_redacted_nominal_result(self) -> None:
        module = self.module()
        self.assertEqual(
            module.GATEWAY_NODE_CONTROL_TRANSIT_TOKEN_TYPE,
            TOKEN_TYPE,
        )
        self.assertEqual(
            (
                module.MAX_GATEWAY_NODE_CONTROL_TRANSIT_HEADER_SEGMENT_BYTES,
                module.MAX_GATEWAY_NODE_CONTROL_TRANSIT_PAYLOAD_SEGMENT_BYTES,
                module.MAX_GATEWAY_NODE_CONTROL_TRANSIT_SIGNATURE_SEGMENT_BYTES,
                module.MAX_GATEWAY_NODE_CONTROL_TRANSIT_CREDENTIAL_BYTES,
            ),
            (
                MAX_HEADER_SEGMENT_BYTES,
                MAX_PAYLOAD_SEGMENT_BYTES,
                MAX_SIGNATURE_SEGMENT_BYTES,
                MAX_CREDENTIAL_BYTES,
            ),
        )
        expected = {
            "GATEWAY_NODE_CONTROL_TRANSIT_TOKEN_TYPE",
            "MAX_GATEWAY_NODE_CONTROL_TRANSIT_HEADER_SEGMENT_BYTES",
            "MAX_GATEWAY_NODE_CONTROL_TRANSIT_PAYLOAD_SEGMENT_BYTES",
            "MAX_GATEWAY_NODE_CONTROL_TRANSIT_SIGNATURE_SEGMENT_BYTES",
            "MAX_GATEWAY_NODE_CONTROL_TRANSIT_CREDENTIAL_BYTES",
            "GatewayNodeControlTransitAdmissionError",
            "VerifiedGatewayNodeControlTransit",
            "Ed25519GatewayNodeControlTransitVerifier",
        }
        for name in expected:
            with self.subTest(name=name):
                self.assertIs(getattr(gateway_root, name), getattr(module, name))
                self.assertIn(name, gateway_root.__all__)

        verified = self.verify_fixture()
        self.assertIsInstance(
            verified,
            module.VerifiedGatewayNodeControlTransit,
        )
        self.assertEqual(verified.effective_now, 150)
        rendered = repr(verified)
        for canary in (
            "cpk-server",
            "workspace-1",
            "gateway-1",
            "router",
            "transit-grant-1",
            self.fixture["credential_ascii"],
        ):
            self.assertNotIn(canary, rendered)

    def test_independent_signed_vector_reconstructs_exact_grant_and_request(self) -> None:
        verified = self.verify_fixture()
        expected_request = NodeControlCommandRequestCodec().decode_canonical_bytes(
            self.fixture_request_bytes()
        )
        expected_grant = DelegatedGatewayNodeControlTransitGrantCodec().decode(
            self.fixture["payload"]["gateway_node_control_transit"]
        )

        self.assertEqual(verified.request, expected_request)
        self.assertEqual(verified.grant, expected_grant)
        self.assertEqual(verified.effective_now, self.fixture["effective_now"])
        self.assertEqual(self.fixture["profile"], TOKEN_TYPE)
        self.assertEqual(len(self.fixture_credential()), 1_432)

    def test_reachable_segment_and_aggregate_maxima_and_next_unit(self) -> None:
        identifier = "a" * 128
        reference = "a" * 256
        target = NodeControlTarget(
            _reference(NodeControlGraphReferenceRole.WORKSPACE, identifier),
            _reference(NodeControlGraphReferenceRole.GRAPH_REVISION, identifier),
            _reference(NodeControlGraphReferenceRole.NODE, identifier),
            _reference(NodeControlGraphReferenceRole.PROVIDER_SOCKET, identifier),
        )
        route_target = _reference(NodeControlGraphReferenceRole.TARGET, identifier)
        request = NodeControlCommandRequest(
            target=target,
            variable_name=_reference(
                NodeControlGraphReferenceRole.VARIABLE,
                identifier,
            ),
            operation=NodeControlOperation.APPLY_COMMAND,
            request_id=identifier,
            idempotency_key=identifier,
            command_codec=ControlPlaneCommandCodec.REPLACE_WEIGHTED_ROUTING_V1,
            precondition=ControlPlaneTransitionPrecondition(1),
            payload=NodeControlPayload(
                ControlPlaneCommandCodec.REPLACE_WEIGHTED_ROUTING_V1,
                WeightedRoutingControlState(
                    targets=(route_target,),
                    weights=((route_target, 1.0),),
                ),
            ),
        )
        grant = DelegatedGatewayNodeControlTransitGrant(
            profile=DelegatedGatewayNodeControlTransitGrantProfile.V1,
            canonicalization=NodeControlCanonicalization.JCS_RFC8785_V1,
            purpose=DelegationKeyPurpose.GATEWAY_NODE_CONTROL_TRANSIT,
            issuer=reference,
            key_id=identifier,
            attempt_id=identifier,
            workspace_id=target.workspace_id,
            graph_revision=target.graph_revision,
            gateway_node_id=_reference(
                NodeControlGraphReferenceRole.NODE,
                identifier,
            ),
            target=target,
            variable_name=request.variable_name,
            operation=request.operation,
            command_codec=request.command_codec,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            request_digest=request.canonical_digest(),
            issued_at=9_007_199_254_740_691,
            not_before=9_007_199_254_740_692,
            expires_at=9_007_199_254_740_991,
            jti=identifier,
        )
        header = {"alg": "EdDSA", "kid": identifier, "typ": TOKEN_TYPE}
        payload = {
            "iss": grant.issuer,
            "aud": grant.audience,
            "iat": grant.issued_at,
            "nbf": grant.not_before,
            "exp": grant.expires_at,
            "jti": grant.jti,
            "gateway_node_control_transit": grant.descriptor(),
        }
        credential = _signed_credential(header, payload)
        protected, claims, signature = credential.split(b".")
        self.assertEqual(
            (len(protected), len(claims), len(signature), len(credential)),
            (
                MAX_HEADER_SEGMENT_BYTES,
                MAX_PAYLOAD_SEGMENT_BYTES,
                MAX_SIGNATURE_SEGMENT_BYTES,
                MAX_CREDENTIAL_BYTES,
            ),
        )
        self.assertEqual(len(grant.canonical_bytes()), 2_834)

        verified = self.verifier(
            issuer=reference,
            workspace_id=identifier,
            gateway_node_id=identifier,
            public_keys=(_public_key(key_id=identifier),),
        ).verify(
            credential=credential,
            request_bytes=request.canonical_bytes(),
            expected_attempt_id=identifier,
            effective_now=grant.not_before,
        )
        self.assertEqual(verified.grant, grant)
        self.assertEqual(verified.request, request)

        verifier = self.verifier()
        candidates = (
            b"x" * (MAX_CREDENTIAL_BYTES + 1),
            b"x" * (MAX_HEADER_SEGMENT_BYTES + 1) + b".e30.AA",
            b"e30." + b"x" * (MAX_PAYLOAD_SEGMENT_BYTES + 1) + b".AA",
            b"e30.e30." + b"x" * (MAX_SIGNATURE_SEGMENT_BYTES + 1),
        )
        for candidate in candidates:
            with self.subTest(length=len(candidate)):
                self.assert_rejected(
                    lambda candidate=candidate: verifier.verify(
                        credential=candidate,
                        request_bytes=self.fixture_request_bytes(),
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    )
                )

    def test_strict_compact_and_canonical_json_rejection_precedence(self) -> None:
        verifier = self.verifier()
        valid_parts = self.fixture_credential().split(b".")

        malformed = (
            "not-bytes",
            bytearray(b"not-bytes"),
            b"",
            b"one",
            b"one.two",
            b"one.two.three.four",
            b"*." + valid_parts[1] + b"." + valid_parts[2],
            valid_parts[0] + b"=." + valid_parts[1] + b"." + valid_parts[2],
        )
        for candidate in malformed:
            with self.subTest(candidate_type=type(candidate).__name__):
                self.assert_rejected(
                    lambda candidate=candidate: verifier.verify(
                        credential=candidate,
                        request_bytes=self.fixture_request_bytes(),
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    )
                )

        duplicate_header = (
            b'{"alg":"EdDSA","alg":"EdDSA","kid":"gateway-transit-key-1",'
            b'"typ":"' + TOKEN_TYPE.encode("ascii") + b'"}'
        )
        payload_bytes = _decode_base64url(valid_parts[1])
        duplicate_payload_bytes = payload_bytes.replace(
            b'{"aud":',
            b'{"aud":"gateway:workspace-1:gateway-1","aud":',
            1,
        )
        deep_payload = b"[" * 300 + b"0" + b"]" * 300
        structural = (
            _base64url(duplicate_header) + b"." + valid_parts[1] + b"." + valid_parts[2],
            valid_parts[0] + b"." + _base64url(duplicate_payload_bytes) + b"." + valid_parts[2],
            _base64url(b'{ "alg":"EdDSA","kid":"gateway-transit-key-1","typ":"' + TOKEN_TYPE.encode("ascii") + b'"}') + b"." + valid_parts[1] + b"." + valid_parts[2],
            valid_parts[0] + b"." + _base64url(b'{"iat":9007199254740992}') + b"." + valid_parts[2],
        )
        for candidate in structural:
            with self.subTest(length=len(candidate)):
                self.assert_rejected(
                    lambda candidate=candidate: verifier.verify(
                        credential=candidate,
                        request_bytes=self.fixture_request_bytes(),
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    )
                )

        deep_candidate = (
            valid_parts[0]
            + b"."
            + _base64url(deep_payload)
            + b"."
            + valid_parts[2]
        )
        with patch.object(
            DelegatedGatewayNodeControlTransitGrantCodec,
            "decode",
            side_effect=AssertionError("nested grant decoder was reached"),
        ):
            self.assert_rejected(
                lambda: verifier.verify(
                    credential=deep_candidate,
                    request_bytes=self.fixture_request_bytes(),
                    expected_attempt_id="attempt-1",
                    effective_now=150,
                )
            )

        excessive_members = {
            f"member_{index}": index
            for index in range(MAX_STRUCTURAL_JSON_MEMBERS + 1)
        }
        excessive_credential = _signed_credential(
            self.fixture["header"],
            excessive_members,
        )
        self.assertLess(
            len(excessive_credential.split(b".")[1]),
            MAX_PAYLOAD_SEGMENT_BYTES,
        )
        with patch.object(
            DelegatedGatewayNodeControlTransitGrantCodec,
            "decode",
            side_effect=AssertionError("nested grant decoder was reached"),
        ), patch.object(
            NodeControlCommandRequestCodec,
            "decode_canonical_bytes",
            side_effect=AssertionError("nested request decoder was reached"),
        ):
            self.assert_rejected(
                lambda: verifier.verify(
                    credential=excessive_credential,
                    request_bytes=self.fixture_request_bytes(),
                    expected_attempt_id="attempt-1",
                    effective_now=150,
                )
            )

        for request_candidate in (
            "not-bytes",
            bytearray(self.fixture_request_bytes()),
            b"x" * 16_385,
        ):
            with self.subTest(request_type=type(request_candidate).__name__):
                self.assert_rejected(
                    lambda request_candidate=request_candidate: verifier.verify(
                        credential=self.fixture_credential(),
                        request_bytes=request_candidate,
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    )
                )

        for change in (
            {"unknown": "candidate-secret"},
            {"typ": None},
        ):
            header = dict(self.fixture["header"])
            if change.get("typ", object()) is None:
                header.pop("typ")
            else:
                header.update(change)
            credential = _signed_credential(header, self.fixture["payload"])
            self.assert_rejected(
                lambda credential=credential: verifier.verify(
                    credential=credential,
                    request_bytes=self.fixture_request_bytes(),
                    expected_attempt_id="attempt-1",
                    effective_now=150,
                ),
                "candidate-secret",
            )

        required_payload_keys = tuple(self.fixture["payload"])
        payload_candidates: list[tuple[str, dict[str, object]]] = []
        for key in required_payload_keys:
            missing = deepcopy(self.fixture["payload"])
            missing.pop(key)
            payload_candidates.append((f"missing-{key}", missing))
        unknown = deepcopy(self.fixture["payload"])
        unknown["unknown"] = "candidate-secret"
        payload_candidates.append(("unknown", unknown))
        wrong_types = {
            "iss": 1,
            "aud": [],
            "iat": "100",
            "nbf": True,
            "exp": 200.5,
            "jti": {},
            "gateway_node_control_transit": [],
        }
        for key, value in wrong_types.items():
            wrong = deepcopy(self.fixture["payload"])
            wrong[key] = value
            payload_candidates.append((f"wrong-{key}", wrong))
        for label, payload in payload_candidates:
            credential = _signed_credential(self.fixture["header"], payload)
            with self.subTest(payload=label):
                self.assert_rejected(
                    lambda credential=credential: verifier.verify(
                        credential=credential,
                        request_bytes=self.fixture_request_bytes(),
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    ),
                    "candidate-secret",
                )

    def test_immutable_bounded_key_snapshot_signature_and_purpose(self) -> None:
        verifier_type = self.contract("Ed25519GatewayNodeControlTransitVerifier")
        error_type = self.contract("GatewayNodeControlTransitAdmissionError")
        workspace = _reference(NodeControlGraphReferenceRole.WORKSPACE, "workspace-1")
        gateway = _reference(NodeControlGraphReferenceRole.NODE, "gateway-1")

        invalid_snapshots = (
            (),
            tuple(_public_key(key_id=f"key-{index}") for index in range(17)),
            (
                _public_key(key_id="candidate-duplicate-key"),
                _public_key(seed=b"b" * 32, key_id="candidate-duplicate-key"),
            ),
            [_public_key(key_id="gateway-transit-key-1")],
        )
        for snapshot in invalid_snapshots:
            with self.subTest(size=len(snapshot)):
                with self.assertRaises(error_type) as caught:
                    verifier_type(
                        issuer="cpk-server",
                        workspace_id=workspace,
                        gateway_node_id=gateway,
                        public_keys=snapshot,
                    )
                self.assertLessEqual(len(str(caught.exception)), 128)
                self.assertNotIn("PUBLIC KEY", str(caught.exception))
                self.assertNotIn("PUBLIC KEY", repr(caught.exception))
                self.assertNotIn("candidate-duplicate-key", str(caught.exception))
                self.assertNotIn("candidate-duplicate-key", repr(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(caught.exception.__context__)

        invalid_authorities = (
            {"issuer": "sk-candidate-secret"},
            {"issuer": "service.internal:8443"},
            {
                "workspace_id": _reference(
                    NodeControlGraphReferenceRole.NODE,
                    "workspace-1",
                )
            },
            {
                "gateway_node_id": _reference(
                    NodeControlGraphReferenceRole.WORKSPACE,
                    "gateway-1",
                )
            },
        )
        for changes in invalid_authorities:
            values = {
                "issuer": "cpk-server",
                "workspace_id": workspace,
                "gateway_node_id": gateway,
                "public_keys": (_public_key(key_id="gateway-transit-key-1"),),
            }
            values.update(changes)
            with self.subTest(changes=changes):
                with self.assertRaises(error_type) as caught:
                    verifier_type(**values)
                self.assertLessEqual(len(str(caught.exception)), 128)
                self.assertNotIn("candidate-secret", str(caught.exception))
                self.assertNotIn("service.internal", str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(caught.exception.__context__)

        second_seed = b"b" * 32
        snapshot = (
            _public_key(key_id="gateway-transit-key-1"),
            _public_key(seed=second_seed, key_id="gateway-transit-key-2"),
        )
        payload = deepcopy(self.fixture["payload"])
        payload["gateway_node_control_transit"]["key_id"] = "gateway-transit-key-2"
        header = dict(self.fixture["header"])
        header["kid"] = "gateway-transit-key-2"
        credential = _signed_credential(header, payload, seed=second_seed)
        verified = self.verifier(public_keys=snapshot).verify(
            credential=credential,
            request_bytes=self.fixture_request_bytes(),
            expected_attempt_id="attempt-1",
            effective_now=150,
        )
        self.assertEqual(verified.grant.key_id, "gateway-transit-key-2")
        self.assertNotIn("PUBLIC KEY", repr(self.verifier(public_keys=snapshot)))

        protected, claims, encoded_signature = credential.split(b".")
        signature = bytearray(_decode_base64url(encoded_signature))
        self.assertEqual(len(signature), 64)
        signature[0] ^= 1
        wrong_signature = protected + b"." + claims + b"." + _base64url(bytes(signature))
        self.assertEqual(len(wrong_signature.split(b".")[2]), 86)
        with patch.object(
            DelegatedGatewayNodeControlTransitGrantCodec,
            "decode",
            side_effect=AssertionError("nested grant decoder was reached"),
        ), patch.object(
            NodeControlCommandRequestCodec,
            "decode_canonical_bytes",
            side_effect=AssertionError("nested request decoder was reached"),
        ):
            self.assert_rejected(
                lambda: self.verifier(public_keys=snapshot).verify(
                    credential=wrong_signature,
                    request_bytes=self.fixture_request_bytes(),
                    expected_attempt_id="attempt-1",
                    effective_now=150,
                )
            )

        payload = deepcopy(self.fixture["payload"])
        payload["gateway_node_control_transit"]["purpose"] = "gateway-probe"
        self.assert_rejected(
            lambda: self.verifier().verify(
                credential=_signed_credential(self.fixture["header"], payload),
                request_bytes=self.fixture_request_bytes(),
                expected_attempt_id="attempt-1",
                effective_now=150,
            )
        )

    def test_outer_inner_claim_request_and_authority_congruence(self) -> None:
        self.module()
        outer_cases = (
            ("iss", "other-issuer"),
            ("aud", "gateway:workspace-1:other"),
            ("iat", 101),
            ("nbf", 101),
            ("exp", 199),
            ("jti", "other-jti"),
        )
        for field, value in outer_cases:
            payload = deepcopy(self.fixture["payload"])
            payload[field] = value
            credential = _signed_credential(self.fixture["header"], payload)
            with self.subTest(field=field):
                self.assert_rejected(
                    lambda credential=credential: self.verifier().verify(
                        credential=credential,
                        request_bytes=self.fixture_request_bytes(),
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    ),
                    str(value),
                )

        grant_cases = (
            ("issuer", "other-issuer"),
            ("attempt_id", "other-attempt"),
            ("workspace_id", "other-workspace"),
            ("graph_revision", "other-revision"),
            ("gateway_node_id", "other-gateway"),
            ("variable_name", "other-variable"),
            ("request_id", "other-request"),
        )
        for field, value in grant_cases:
            payload = deepcopy(self.fixture["payload"])
            payload["gateway_node_control_transit"][field] = value
            credential = _signed_credential(self.fixture["header"], payload)
            with self.subTest(field=field):
                self.assert_rejected(
                    lambda credential=credential: self.verifier().verify(
                        credential=credential,
                        request_bytes=self.fixture_request_bytes(),
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    ),
                    value,
                )

        changed_request = deepcopy(self.fixture["request"])
        changed_request["request_id"] = "other-request"
        self.assert_rejected(
            lambda: self.verifier().verify(
                credential=self.fixture_credential(),
                request_bytes=rfc8785.dumps(changed_request),
                expected_attempt_id="attempt-1",
                effective_now=150,
            ),
            "other-request",
        )

    def test_explicit_trusted_effective_time_edges_without_hidden_clock(self) -> None:
        self.assertEqual(self.verify_fixture(effective_now=100).effective_now, 100)
        for value in (99, 200, True, 150.0, -1, 9_007_199_254_740_992):
            with self.subTest(effective_now=value):
                self.assert_rejected(
                    lambda value=value: self.verify_fixture(effective_now=value),
                    str(value),
                )
        for attempt_id in (True, "", "a" * 129, "sk-candidate-secret"):
            with self.subTest(expected_attempt_id=attempt_id):
                self.assert_rejected(
                    lambda attempt_id=attempt_id: self.verify_fixture(
                        expected_attempt_id=attempt_id
                    ),
                    str(attempt_id),
                )

        module = self.module()
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(
            imported.isdisjoint(
                {
                    "time",
                    "datetime",
                    "sqlite3",
                    "threading",
                    "control_plane_kit_operations",
                }
            )
        )

    def test_authority_families_errors_and_private_ownership_are_closed(self) -> None:
        request = NodeControlCommandRequestCodec().decode_canonical_bytes(
            self.fixture_request_bytes()
        )
        grant = DelegatedGatewayNodeControlTransitGrantCodec().decode(
            self.fixture["payload"]["gateway_node_control_transit"]
        )
        workload = DelegatedWorkloadNodeControlGrant(
            issuer=grant.issuer,
            key_id=grant.key_id,
            audience="workload:router:control",
            target=request.target,
            variable_name=request.variable_name,
            operation=request.operation,
            command_codec=request.command_codec,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            request_digest=request.canonical_digest(),
            issued_at=100,
            not_before=100,
            expires_at=200,
            jti="workload-grant-1",
        )
        surface_request = NodeControlSurfaceReadRequest(
            target=request.target,
            kind=NodeControlSurfaceReadKind.CAPABILITIES,
            declaration_identity=WorkloadNodeControlSurfaceDeclarationIdentity(
                "a" * 64
            ),
            request_id="surface-read-1",
        )
        surface = DelegatedWorkloadNodeControlSurfaceReadGrant(
            profile=DelegatedWorkloadNodeControlSurfaceReadGrantProfile.V1,
            canonicalization=NodeControlCanonicalization.JCS_RFC8785_V1,
            purpose=DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
            issuer=grant.issuer,
            key_id=grant.key_id,
            audience="workload:router:control",
            target=surface_request.target,
            kind=surface_request.kind,
            declaration_identity=surface_request.declaration_identity,
            request_id=surface_request.request_id,
            request_digest=surface_request.canonical_digest(),
            issued_at=100,
            not_before=100,
            expires_at=200,
            jti="surface-grant-1",
        )
        probe_request = GatewayProbeRequest(
            GatewayProbeCommandKind.HTTP_STATUS,
            GatewayTargetId("router.internal"),
            "/health",
        )
        probe = DelegatedGatewayProbeGrant(
            issuer=grant.issuer,
            key_id=grant.key_id,
            audience=grant.audience,
            workspace_id="workspace-1",
            operation_id="operation-1",
            request_id="probe-1",
            gateway_node_id="gateway-1",
            probe_kind=probe_request.kind,
            target_id=probe_request.target_id,
            request_digest=probe_request.canonical_digest(),
            issued_at=100,
            expires_at=200,
            jti="probe-grant-1",
        )
        substitutions = (
            ("workload_node_control", workload.descriptor()),
            ("workload_node_control_surface_read", surface.descriptor()),
            ("gateway_probe", probe.descriptor()),
        )
        self.module()
        for field, descriptor in substitutions:
            payload = {
                "iss": grant.issuer,
                "aud": grant.audience,
                "iat": 100,
                "nbf": 100,
                "exp": 200,
                "jti": descriptor["jti"],
                field: descriptor,
            }
            credential = _signed_credential(self.fixture["header"], payload)
            with self.subTest(family=field):
                self.assert_rejected(
                    lambda credential=credential: self.verifier().verify(
                        credential=credential,
                        request_bytes=self.fixture_request_bytes(),
                        expected_attempt_id="attempt-1",
                        effective_now=150,
                    )
                )

        self.assert_rejected(
            lambda: self.verifier().verify(
                credential=grant,
                request_bytes=self.fixture_request_bytes(),
                expected_attempt_id="attempt-1",
                effective_now=150,
            )
        )

        module = self.module()
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(
            imported.isdisjoint(
                {
                    "fastapi",
                    "httpx",
                    "requests",
                    "socket",
                    "sqlite3",
                    "control_plane_kit_operations",
                    "control_plane_kit_server_sdk",
                }
            )
        )
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        }
        self.assertTrue(
            definitions.isdisjoint(
                {
                    "sign",
                    "consume",
                    "remember_once",
                    "resolve_target",
                    "dispatch",
                    "create_app",
                }
            )
        )
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertNotIn("Ed25519PrivateKey", imported_names)
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sign"
                for node in ast.walk(tree)
            )
        )
        for handler in (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
        ):
            self.assertIsNotNone(handler.type)
            if isinstance(handler.type, ast.Name):
                self.assertNotIn(handler.type.id, {"Exception", "BaseException"})


if __name__ == "__main__":
    unittest.main()
