"""Proposed #379 private admission boundary; synthetic protected input only.

Tests-only review checkpoint. Production adapter has not been implemented.
"""
import importlib
import json
import unittest

from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind


ISSUER = "urn:control-plane-kit:static-development"
MODULE = "control_plane_kit_servers_cpk_server.supplied_child_auth"


class SuppliedChildAuthInterfaceTests(unittest.TestCase):
    def test_proposed_interface_is_available(self):
        api = importlib.import_module(MODULE)
        self.assertTrue(callable(api.validate_child_auth_documents))
        self.assertTrue(issubclass(api.SuppliedChildAuthError, ValueError))


class SuppliedChildAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # An absent adapter is one class prerequisite error, not behavioral red
        # for every proposed denial case. No case is skipped or replaced.
        cls.api = importlib.import_module(MODULE)

    def setUp(self):
        self.identities = {
            role: PrincipalIdentity(ISSUER, "child-a-" + role, PrincipalKind.OPERATOR)
            for role in ("administrator", "initializer", "browser")
        }
        self.document = [
            {"credential": "synthetic-private-" + role, "subject_id": identity.subject_id,
             "kind": identity.kind.value, "workspace_grants": {}}
            for role, identity in self.identities.items()
        ]
        self.policy = {
            "schema": "cpk-server.workspace-authority.v1", "installation_id": "child-a",
            "administrators": [self.identities["administrator"].descriptor()],
            "known_identities": [identity.descriptor() for identity in self.identities.values()],
            "capabilities": [],
        }

    def validate(self, **changes):
        values = {
            "child_installation_id": "child-a", **self.identities,
            "verifier_document": json.dumps(self.document).encode("ascii"),
            "authority_document": json.dumps(self.policy).encode("ascii"),
        }
        return self.api.validate_child_auth_documents(**{**values, **changes})

    def refused(self, **changes):
        with self.assertRaises(self.api.SuppliedChildAuthError) as caught:
            self.validate(**changes)
        error = caught.exception
        self.assertEqual(str(error), "supplied child authentication configuration is invalid")
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertNotIn("synthetic-private", repr(error))

    def test_exact_supplied_three_principal_profile_is_accepted_without_returning_material(self):
        self.assertIsNone(self.validate())
        self.document.reverse()
        self.policy["known_identities"].reverse()
        self.assertIsNone(self.validate())

    def test_missing_extra_and_duplicate_identity_are_refused(self):
        original = list(self.document)
        self.document = original[:2]
        self.refused()
        self.document = original + [{**original[0], "subject_id": "foreign", "credential": "synthetic-private-foreign"}]
        self.refused()
        self.document = [*original[:2], {**original[2], "subject_id": original[1]["subject_id"]}]
        self.refused()

    def test_static_workspace_grant_and_duplicate_bearer_are_refused(self):
        self.document[1]["workspace_grants"] = {"child-workspace": ["instance:workspace:read"]}
        self.refused()
        self.document[1]["workspace_grants"] = {}
        self.document[1]["credential"] = self.document[0]["credential"]
        self.refused()

    def test_full_typed_identity_and_distinct_roles_are_required(self):
        self.refused(browser=PrincipalIdentity("foreign-issuer", "child-a-browser", PrincipalKind.OPERATOR))
        self.refused(browser=PrincipalIdentity(ISSUER, "child-a-browser", PrincipalKind.WORKER))
        self.refused(browser=self.identities["initializer"])

    def test_policy_requires_exact_child_single_administrator_and_known_identities(self):
        self.refused(child_installation_id="child-b")
        original = list(self.policy["administrators"])
        self.policy["administrators"].append(self.identities["initializer"].descriptor())
        self.refused()
        self.policy["administrators"] = original
        self.policy["administrators"] = [self.identities["initializer"].descriptor()]
        self.refused()
        self.policy["administrators"] = original
        known = list(self.policy["known_identities"])
        self.policy["known_identities"] = self.policy["known_identities"][:2]
        self.refused()
        self.policy["known_identities"] = [*known, PrincipalIdentity(
            ISSUER, "policy-only-foreign", PrincipalKind.OPERATOR).descriptor()]
        self.refused()

    def test_conflicting_duplicate_verifier_keys_are_refused(self):
        raw = json.dumps(self.document).encode("ascii")
        for key, existing, conflicting in (
            (b"credential", b"synthetic-private-administrator", b"synthetic-private-foreign"),
            (b"subject_id", b"child-a-administrator", b"child-a-foreign"),
        ):
            with self.subTest(key=key):
                field = b'"' + key + b'": "' + existing + b'"'
                conflict = b'"' + key + b'": "' + conflicting + b'", '
                # Keep the intended value last, so a permissive JSON decoder
                # would otherwise accept the profile after discarding conflict.
                self.refused(verifier_document=raw.replace(field, conflict + field, 1))

    def test_unexpected_field_on_valid_verifier_entry_is_refused(self):
        self.document[0]["unexpected"] = "synthetic-private-unrecognized"
        self.refused()

    def test_invalid_private_bytes_have_fixed_detached_failure(self):
        self.refused(verifier_document=b'{"synthetic-private-input":')
        self.refused(authority_document=b'{"synthetic-private-input":')
        self.refused(verifier_document=b"x" * 131073)
        raw = json.dumps(self.document).encode("ascii")
        self.refused(verifier_document=raw + b" " * (131073 - len(raw)))


if __name__ == "__main__":
    unittest.main()
