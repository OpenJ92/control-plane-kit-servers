Source: [managed_provider_selection_acceptance.py](../../../../../products/cpk_server/tests/managed_provider_selection_acceptance.py).

This pending #341 target extends the existing isolated PostgreSQL/public factory
witness with actual management-grant composition. Public HTTP/MCP writes grant
the configured administrator explicit runtime registration/revocation scopes,
register a local runtime, grant/revoke/regrant management access, then revoke the
runtime authority. A read-only owner-store lookup obtains the real typed runtime
record for the selector interface; no mutation or admitted history is seeded.

Regrant chooses a second installed capability/configuration, so exact mapping is
observable rather than inferred from a one-entry catalog. A separately publicly
registered authority without an assignment remains unselected. One same-material
registration attempt after revocation is expected to refuse through the selected
owner's current generic500 boundary; current selection and revoked assignment
are checked afterward. This records the deterministic-ID/retained-row limitation,
not a successful new incarnation or a promise that500 is an ideal public API.

The actual ManagedRuntimeSelectionService must expose absence, the fixed installed
acquisition policy, management revocation and current runtime-authority revocation.
An old active input record must not bypass current stored revocation. Unknown
registration input is only refusal evidence, not successful re-registration.
The remaining public payloads/results follow the selected existing owners.

Only Docker construction entrypoints are intercepted as no-I/O sentinels; no
permission store/selection service/state machine is replaced. The installed
private acquisition configuration must not appear in public administration data.
The same existing schema context owns exact cleanup. This target is unvalidated;
it does not execute a Docker provider, establish daemon identity, prove fresh
effect admission, or claim live/re-registration support. Final markers occur
only after this helper returns and the enclosing schema cleanup completes.
