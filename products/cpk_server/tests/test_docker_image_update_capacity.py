"""Temporary diagnostic pass-through and redaction; no owner-state simulation."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import docker_image_update_capacity as diagnostic
from control_plane_kit_operations.configuration_preparation import ConfigurationEvidenceFootprint as Footprint
from control_plane_kit_operations.postgres.configuration_acceptance_store import ConfigurationAcceptanceStore


class PublicationBudgetDiagnosticTests(unittest.TestCase):
    def fixture(self):
        prior, snapshot = Footprint(1, 2, 3, 4), Footprint(5, 6, 7, 8)
        future = SimpleNamespace(settled=Footprint(9, 10, 11, 12), peak=Footprint(13, 14, 15, 16))
        publication = SimpleNamespace(settled=Footprint(17, 18, 19, 20), peak=Footprint(4096, 22, 23, 24))
        prepared = SimpleNamespace(evidence_read=SimpleNamespace(used=prior), event=None,
            payload="PRIVATE-PAYLOAD", history="PRIVATE-HISTORY", secret="PRIVATE-SECRET")
        return prepared, (snapshot, future, publication)

    def test_exact_forecast_passes_once_with_bounded_numeric_output_and_restoration(self):
        prepared, result = self.fixture()
        original, preflight = ConfigurationAcceptanceStore._publication_budgets, ConfigurationAcceptanceStore._preflight
        with patch.object(ConfigurationAcceptanceStore, "_publication_budgets", Mock(return_value=result)) as owner:
            with patch("builtins.print") as output, diagnostic.observe_publication_budgets():
                store = ConfigurationAcceptanceStore(None)
                for index in range(10):
                    prepared.event = None if index % 2 == 0 else object()
                    self.assertIs(store._publication_budgets(prepared), result)
                self.assertIs(ConfigurationAcceptanceStore._preflight, preflight)
            self.assertIs(ConfigurationAcceptanceStore._publication_budgets, owner)
            self.assertEqual(owner.call_count, 10)
            self.assertTrue(all(call.args == (store, prepared) for call in owner.call_args_list))
        self.assertIs(ConfigurationAcceptanceStore._publication_budgets, original)
        self.assertEqual(output.call_count, 8)
        rows = [json.loads(call.args[0]) for call in output.call_args_list]
        self.assertEqual([row["publication_budget_diagnostic"] for row in rows], list(range(1, 9)))
        self.assertEqual({row["phase"] for row in rows}, {"pre-id", "bound"})
        names = {"prior", "snapshot", "future_settled", "future_peak", "publication_settled",
            "publication_peak", "combined_settled", "combined_peak"}
        self.assertEqual(set(rows[0]), names | {"phase", "publication_budget_diagnostic"})
        for row in rows:
            for name in names:
                self.assertEqual(set(row[name]), {"records", "value_octets", "scalar_markers",
                    "statements", "accounted_bytes", "decision"})
            self.assertEqual(row["combined_peak"]["records"], 4097)
            self.assertEqual(row["combined_peak"]["decision"], "record-limit")
        self.assertNotIn("PRIVATE", json.dumps(rows))
        self.assertEqual(prepared.evidence_read.used, Footprint(1, 2, 3, 4))

    def test_owner_exception_is_identical_and_patch_restores_on_failure(self):
        prepared, _ = self.fixture()
        error = ValueError("PRIVATE-OWNER-FAILURE")
        original = ConfigurationAcceptanceStore._publication_budgets
        with patch.object(ConfigurationAcceptanceStore, "_publication_budgets", Mock(side_effect=error)) as owner:
            with patch("builtins.print") as output:
                with self.assertRaises(ValueError) as caught:
                    with diagnostic.observe_publication_budgets():
                        ConfigurationAcceptanceStore(None)._publication_budgets(prepared)
                self.assertIs(caught.exception, error)
                owner.assert_called_once()
                output.assert_not_called()
            self.assertIs(ConfigurationAcceptanceStore._publication_budgets, owner)
        self.assertIs(ConfigurationAcceptanceStore._publication_budgets, original)

    def test_output_failure_preserves_actual_preflight_refusal(self):
        from control_plane_kit_operations.postgres.configuration_evidence import _Capacity
        prepared, result = self.fixture()
        original = ConfigurationAcceptanceStore._publication_budgets
        with patch.object(ConfigurationAcceptanceStore, "_publication_budgets", Mock(return_value=result)) as owner:
            with patch("builtins.print", side_effect=OSError("PRIVATE-OUTPUT-FAILURE")) as output:
                with self.assertRaises(_Capacity):
                    with diagnostic.observe_publication_budgets():
                        ConfigurationAcceptanceStore(None)._preflight(prepared)
                output.assert_called_once()
                owner.assert_called_once()
        self.assertIs(ConfigurationAcceptanceStore._publication_budgets, original)
        self.assertEqual(prepared.evidence_read.used, Footprint(1, 2, 3, 4))

    def test_formatting_and_numeric_bounds_cannot_change_original_return(self):
        for mode in ("serialization", "overflow", "numeric-bound"):
            with self.subTest(mode=mode):
                prepared, result = self.fixture()
                if mode == "numeric-bound":
                    prepared.evidence_read.used = Footprint(2**63, 0, 0, 0)
                options = {"side_effect": ValueError("PRIVATE-FORMAT")} if mode == "serialization" else {
                    "return_value": "x" * 16385}
                with patch.object(ConfigurationAcceptanceStore, "_publication_budgets", Mock(return_value=result)) as owner:
                    with patch.object(diagnostic.json, "dumps", **options), patch("builtins.print") as output:
                        with diagnostic.observe_publication_budgets():
                            self.assertIs(ConfigurationAcceptanceStore(None)._publication_budgets(prepared), result)
                        owner.assert_called_once()
                        output.assert_not_called()
