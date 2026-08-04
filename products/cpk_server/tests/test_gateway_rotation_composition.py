from contextlib import contextmanager
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import httpx

from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.secrets import (
    SecretCustodyGrant,
    SecretCustodyStatus,
    SecretProviderEndpointReference,
    SecretReference,
    SecretUseIntent,
    SecretVersionRevocationGrant,
    SecretVersionRevocationReceipt,
)
from control_plane_kit_operations import (
    DelegationKeyGenerationGrant,
    GatewayKeyGenerationOutcome,
    GatewayKeyRotationRevocationEffectOutcome,
)
from control_plane_kit_interpreters.secret_provider import (
    SecretProviderBootstrapRegistry,
    SecretProviderClientCode,
    SecretProviderClientError,
    SecretProviderOutcomeCertainty,
    canonical_provider_secret_id,
)


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"
ENDPOINT = SecretProviderEndpointReference("provider-main")
CREDENTIAL = SecretReference("secret://bootstrap/provider-token")
REFERENCE = SecretReference("secret://provider-main/gateway/key-b")
PUBLIC_KEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEA7P+6pMvjtSXnpOCuaS+0dvj1Hx+fiZLTdfi0CPbNKgY=\n"
    "-----END PUBLIC KEY-----\n"
)


@contextmanager
def _server_module():
    sys.path.insert(0, str(PRODUCT_SRC))
    try:
        yield importlib.import_module("control_plane_kit_servers_cpk_server.server")
    finally:
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)


@contextmanager
def _provider_registry():
    with tempfile.TemporaryDirectory() as directory:
        credential_path = Path(directory) / "provider.token"
        credential_path.write_text(
            "provider-credential-not-for-output\n",
            encoding="ascii",
        )
        yield SecretProviderBootstrapRegistry(
            endpoints={ENDPOINT: "https://secrets.internal.example"},
            credential_files={CREDENTIAL: credential_path},
        )


def _generation_grant() -> DelegationKeyGenerationGrant:
    return DelegationKeyGenerationGrant(
        SecretCustodyGrant(
            custody_id="scust_" + "a" * 64,
            workspace_id="workspace-a",
            provider_registration_id="sprov_" + "b" * 64,
            endpoint_reference=ENDPOINT,
            credential_reference=CREDENTIAL,
            reference=REFERENCE,
            intent=SecretUseIntent.GATEWAY_PROBE_SIGNING_KEY,
            actor_subject="operator-a",
            correlation_id="rotation-key-b",
            custody_fingerprint="c" * 64,
        ),
        DelegationKeyPurpose.GATEWAY_PROBE,
        "cpk-server",
        "2026-08-04T00:00:00Z",
    )


def _generation_response() -> dict[str, object]:
    return {
        "outcome": "generated",
        "secret_reference": REFERENCE.reference_id,
        "metadata": {
            "workspace_id": "workspace-a",
            "secret_id": canonical_provider_secret_id(REFERENCE),
            "version_id": "version-b",
            "version_number": 2,
            "status": "active",
            "algorithm": "AES-256-GCM",
            "key_fingerprint": "d" * 64,
            "key_version": "test",
            "labels": {
                "intent": "gateway.probe-signing-key",
                "purpose": "gateway-probe",
                "issuer": "cpk-server",
                "key_id": "gateway-key-b",
            },
            "created_at": "2026-08-04T00:00:00Z",
            "revoked_at": None,
        },
        "purpose": "gateway-probe",
        "issuer": "cpk-server",
        "correlation_id": "rotation-key-b",
        "key_id": "gateway-key-b",
        "algorithm": "ed25519",
        "public_key_pem": PUBLIC_KEY_PEM,
        "fingerprint_sha256": sha256(PUBLIC_KEY_PEM.encode("ascii")).hexdigest(),
        "replayed": False,
    }


class GatewayRotationCompositionTests(unittest.TestCase):
    def test_provider_composition_reuses_one_redacted_bootstrap_registry(self) -> None:
        with _server_module() as server, tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "provider.token"
            credential_path.write_text(
                "provider-credential-not-for-output\n",
                encoding="ascii",
            )
            config = server.CpkServerBootstrapConfiguration.from_environment(
                {
                    "CPK_SERVER_MODE": "execution-capable",
                    "CPK_CONTROL_AUTH_CONFIGURED": "true",
                    "CPK_PORT": "8080",
                    "CPK_RUNTIME_INTERPRETERS": "none",
                    "CPK_PRODUCT_MATERIAL_RESOLVER": "provider",
                    "CPK_MATERIAL_PROVIDER_ROUTES_JSON": json.dumps(
                        {"provider-main": "https://secrets.internal.example"}
                    ),
                    "CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON": json.dumps(
                        {CREDENTIAL.reference_id: str(credential_path)}
                    ),
                    "CPK_WORKPLACE_DATABASE_URL": "postgres://user:pass@db/cpk",
                    "CPK_ACTIVITY_HISTORY_DATABASE_URL": "postgres://user:pass@db/cpk",
                    "CPK_OBSERVER_STATE_DATABASE_URL": "postgres://user:pass@db/cpk",
                    "CPK_GRAPH_TOPOLOGY_DATABASE_URL": "postgres://user:pass@db/cpk",
                }
            )
            transport = httpx.MockTransport(
                lambda _request: httpx.Response(500, json={})
            )
            composition = server._secret_provider_composition(
                config,
                transport=transport,
            )

            self.assertIs(
                composition.bootstrap_registry,
                composition.authorized_resolver.bootstrap_registry,
            )
            self.assertIs(
                composition.bootstrap_registry,
                composition.secret_custodian.bootstrap_registry,
            )
            self.assertIs(composition.transport, transport)
            self.assertEqual(
                repr(composition),
                "SecretProviderComposition(configured=True)",
            )
            for forbidden in (
                "provider-credential-not-for-output",
                str(credential_path),
                "secrets.internal.example",
            ):
                self.assertNotIn(forbidden, repr(composition))

    def test_generation_adapter_returns_only_public_version_evidence(self) -> None:
        observed: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            observed.append(
                {
                    "authorization": request.headers["authorization"],
                    "path": request.url.path,
                    "body": json.loads(request.content),
                }
            )
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json=_generation_response(),
            )

        with _server_module() as server, _provider_registry() as registry:
            result = server._GatewayRotationGenerationAdapter(
                registry,
                httpx.MockTransport(handler),
            ).generate(_generation_grant())

        self.assertIs(result.outcome, GatewayKeyGenerationOutcome.GENERATED)
        self.assertEqual(result.evidence.workspace_id, "workspace-a")
        self.assertEqual(result.evidence.reference, REFERENCE)
        self.assertEqual(result.evidence.version_id, "version-b")
        self.assertEqual(result.evidence.public_key.key_id, "gateway-key-b")
        self.assertEqual(
            observed[0]["path"],
            (
                "/v1/workspaces/workspace-a/delegation-keys/"
                f"{canonical_provider_secret_id(REFERENCE)}/generate"
            ),
        )
        self.assertEqual(
            observed[0]["body"],
            {
                "secret_reference": REFERENCE.reference_id,
                "purpose": "gateway-probe",
                "issuer": "cpk-server",
                "caller_subject": "operator-a",
                "correlation_id": "rotation-key-b",
            },
        )
        self.assertEqual(
            observed[0]["authorization"],
            "Bearer provider-credential-not-for-output",
        )
        self.assertNotIn("provider-credential-not-for-output", repr(result))

    def test_generation_adapter_preserves_definite_and_uncertain_outcomes(self) -> None:
        cases = (
            (
                lambda _request: httpx.Response(
                    403,
                    headers={"content-type": "application/json"},
                    json={
                        "detail": {
                            "outcome": "denied",
                            "code": "insufficient-scope",
                        }
                    },
                ),
                GatewayKeyGenerationOutcome.DEFINITE_FAILURE,
                "provider-denied",
            ),
            (
                lambda _request: httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    json={},
                ),
                GatewayKeyGenerationOutcome.UNCERTAIN,
                "provider-malformed-response",
            ),
        )
        with _server_module() as server, _provider_registry() as registry:
            for handler, expected, code in cases:
                with self.subTest(expected=expected):
                    result = server._GatewayRotationGenerationAdapter(
                        registry,
                        httpx.MockTransport(handler),
                    ).generate(_generation_grant())
                    self.assertIs(result.outcome, expected)
                    self.assertEqual(result.failure_code, code)

    def test_revocation_adapter_uses_exact_grant_and_bounds_uncertainty(self) -> None:
        reference = SecretReference("secret://provider-main/gateway/key-a")
        grant = SecretVersionRevocationGrant(
            revocation_id="srevoke_" + "a" * 64,
            workspace_id="workspace-a",
            provider_registration_id="sprov_" + "b" * 64,
            endpoint_reference=ENDPOINT,
            credential_reference=CREDENTIAL,
            reference=reference,
            version_id="version-a",
            version_number=1,
            actor_subject="rotation-program",
            correlation_id="retire-key-a",
            revocation_fingerprint="c" * 64,
        )
        receipt = SecretVersionRevocationReceipt(
            revocation_id=grant.revocation_id,
            provider_registration_id=grant.provider_registration_id,
            reference=reference,
            version_id="version-a",
            version_number=1,
            status=SecretCustodyStatus.REVOKED,
        )

        class RecordingCustodian:
            def __init__(self) -> None:
                self.received = []

            def revoke_version(self, received):
                self.received.append(received)
                return receipt

        class UncertainCustodian:
            def revoke_version(self, _received):
                raise SecretProviderClientError(
                    SecretProviderClientCode.TRANSPORT_FAILED,
                    certainty=SecretProviderOutcomeCertainty.UNCERTAIN,
                )

        with _server_module() as server:
            custodian = RecordingCustodian()
            result = server._GatewayRotationRevocationAdapter(
                custodian
            ).revoke_version(grant)
            uncertain = server._GatewayRotationRevocationAdapter(
                UncertainCustodian()
            ).revoke_version(grant)

        self.assertEqual(custodian.received, [grant])
        self.assertIs(
            result.outcome,
            GatewayKeyRotationRevocationEffectOutcome.REVOKED,
        )
        self.assertEqual(result.receipt, receipt)
        self.assertIs(
            uncertain.outcome,
            GatewayKeyRotationRevocationEffectOutcome.UNCERTAIN,
        )
        self.assertEqual(uncertain.failure_code, "provider-transport-failed")


if __name__ == "__main__":
    unittest.main()
