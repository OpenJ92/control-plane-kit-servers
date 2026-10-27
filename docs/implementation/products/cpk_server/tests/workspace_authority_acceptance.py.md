Source: [workspace_authority_acceptance.py](../../../../../products/cpk_server/tests/workspace_authority_acceptance.py).

This #341 witness calls the actual server startup and shared Operations factory
over the existing smoke's isolated PostgreSQL schema. Synthetic credentials
identify a configured administrator and three distinct full identities. No
permission store, command service, resolver or state transition is replaced.

Before startup can succeed, the witness explicitly initializes its disposable
installation through WorkspacePermissionCommandService. Missing and mismatched
receipts must refuse before provider composition. The fixture's initialization
is not startup seeding or retained-installation migration.

Public HTTP/MCP create two workspaces, deny access before a grant, expose a grant
on the next request, preserve identity/workspace isolation, exercise public
replay/conflict mapping, and deny subsequent reads after revocation. Reconstructing
the app retains the revoked record despite stale grants in the unchanged verifier.
Requests and retained responses are bounded, and credential values must not
appear in public output. The existing schema context owns exact cleanup.

The witness is unvalidated at the test-only checkpoint. It proves no management
transport selection, provider execution, retained-installation upgrade, physical
daemon identity or live deployment. The normal Docker gate must actually reach
it before any public composition credit is claimed.

The initial test-only run40582411630 stopped at package-integrity after 26 support
tests: the expected-refusal helper used an exception handler containing `pass`.
No package target or this witness ran. The narrow correction uses standard
`unittest.TestCase.assertRaises` and retains the no-provider-call assertion;
wrong exceptions and unexpected success still fail. The integrity rule and
runner are unchanged. A corrected owning attempt remains unvalidated.

Implementation run40584390699 passed all package tests and reached this witness's
permission inspect, which returned400. Its TestClient params used form-style
plus signs for JSON spaces, while the established strict percent decoder retains
literal plus signs. GET requests now build a percent-encoded URL with the standard
urlencode(..., quote_via=quote), matching the existing transport target. JSON
values, identities, expected responses and production decoding remain unchanged;
this also preserves spaces and literal plus signs inside values. Inspect/revoke/
restart and the complete witness still require a successful subsequent run.

Run40585946487 proved the strict-percent inspection and revision1/scopes result,
then reached a malformed MCP revoke payload: the accepted API requires exact
scopes to remove. The witness now supplies the actually inspected record's scopes,
retaining target/revision/idempotency and all expected results. The production
contract is unchanged. Post-revoke denial, restart preservation and final PASS
remain unvalidated. Remaining request shapes are checked against the selected
public owners before retry, without recreating their state transitions here.

The next selector target adds two existing opaque capabilities to this trusted
installation policy and calls managed_provider_selection_acceptance after the
original restart/empty-permission assertions. All original assertions remain.
The helper uses the same actual app, public request transport and isolated schema;
its separate marker is printed after enclosing cleanup. This extension is
unvalidated and does not rewrite the accepted factory/startup run40587396766.
