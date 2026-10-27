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
