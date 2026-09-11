Source: [products/cpk_server/tests/test_hosted_gateway_delegation_bootstrap.py](../../../../../products/cpk_server/tests/test_hosted_gateway_delegation_bootstrap.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests load the hosted controller under a temporary module identity and
replace its HTTP/MCP calls. Desired-graph cases require reading the workspace
pointer first, carrying its projection/revision fence into the command, rejecting
a stale expected graph before writing, and preserving an unassigned pointer.

The delegation case records provider registration, reference registration, key
admission, activation and final public readback in order. It checks selected
scope/reference fields and a matching active key with the normalized public-PEM
fingerprint. This file covers the successful readback; malformed/mismatched
readback rejection is visible in the controller but is not separately exercised
here. Scripted public responses do not establish server admission, private-key
possession, real signing or provider persistence.

A final test inspects source text for provider mode, bootstrap mode selection,
restart-call count and readiness-policy wiring. Its name does not turn those
substring checks into an executed restart/replay witness. The source-live
controller and shell own actual effect sequencing and cleanup.

Related source: [hosted controller](../../../../../scripts/cpk_server_hosted_activity.py),
[source-live controller](../../../../../scripts/cpk_server_secret_provider_source_live.py),
[source-live launcher](../../../../../scripts/cpk_server_secret_provider_source_live_smoke.sh).
