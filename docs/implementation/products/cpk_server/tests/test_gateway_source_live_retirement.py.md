Source: [products/cpk_server/tests/test_gateway_source_live_retirement.py](../../../../../products/cpk_server/tests/test_gateway_source_live_retirement.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These are AST/text retirement guards. They exclude named obsolete scenario,
facade and route spellings; require the selected verifier controller to contain
success-probe calls before the denial-matrix call and before its earliest return;
and check published/custody launcher configuration strings.

The call-line comparison is lexical, not control-flow or execution analysis.
Presence/absence checks cover named source constructs, not every possible
equivalent implementation. They neither execute the denial matrix nor verify
published image bytes, live custody or cleanup.

Related source: [published gateway launcher](../../../scripts/cpk_server_gateway_published_live_smoke.sh.md),
[hosted source](../../../../../scripts/cpk_server_hosted_activity.py),
[custody launcher](../../../../../scripts/cpk_server_cloudflare_secret_custody_source_live_smoke.sh).

Controller owner: [source-live controller](../../../../../scripts/cpk_server_secret_provider_source_live.py).
