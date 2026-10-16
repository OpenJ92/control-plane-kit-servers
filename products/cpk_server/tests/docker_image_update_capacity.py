"""Temporary #1993 numeric observation of the actual installed owner forecast."""
from contextlib import contextmanager
import json
from unittest.mock import patch


def _emit(prepared, result, ordinal):
    from control_plane_kit_operations.configuration_preparation import configuration_evidence_capacity

    def numbers(value):
        fields = ("records", "value_octets", "scalar_markers", "statements", "accounted_bytes")
        row = {name: getattr(value, name) for name in fields}
        if any(type(number) is not int or not 0 <= number <= 2**63 - 1 for number in row.values()):
            raise ValueError("diagnostic footprint is outside its numeric bound")
        decision = configuration_evidence_capacity(value).value
        if decision not in {"within-limits", "record-limit", "byte-limit"}:
            raise ValueError("diagnostic capacity decision is unsupported")
        return {**row, "decision": decision}

    snapshot, future, publication = result
    prior = prepared.evidence_read.used
    record = {"publication_budget_diagnostic": ordinal,
        "phase": "pre-id" if prepared.event is None else "bound",
        "prior": numbers(prior), "snapshot": numbers(snapshot),
        "future_settled": numbers(future.settled), "future_peak": numbers(future.peak),
        "publication_settled": numbers(publication.settled), "publication_peak": numbers(publication.peak),
        "combined_settled": numbers(prior.plus(publication.settled)),
        "combined_peak": numbers(prior.plus(publication.peak))}
    encoded = json.dumps(record, sort_keys=True)
    if len(encoded.encode("utf-8")) > 16384:
        raise ValueError("diagnostic output exceeds its bound")
    print(encoded, flush=True)


@contextmanager
def observe_publication_budgets():
    """Return original forecasts; leave preflight, counters and refusal untouched."""
    from control_plane_kit_operations.postgres.configuration_acceptance_store import ConfigurationAcceptanceStore

    original = ConfigurationAcceptanceStore._publication_budgets
    count = 0

    def observed(store, prepared):
        nonlocal count
        result = original(store, prepared)
        if count < 8:
            count += 1
            try:
                _emit(prepared, result, count)
            except Exception:
                pass  # Diagnostic output cannot change the original owner's outcome.
        return result

    with patch.object(ConfigurationAcceptanceStore, "_publication_budgets", observed):
        yield
