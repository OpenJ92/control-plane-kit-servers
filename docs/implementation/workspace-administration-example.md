# Separate workspace permissions and runtime management

These source examples describe the selected public HTTP/client contracts for
Servers #341. They are not an installation script or a live execution approval.
The supported dynamic-bootstrap prerequisite must provide trusted policy,
explicit initialization and protected delivery before a fresh installation can
use these commands. Normal process startup requires the existing owner receipt;
it never initializes or imports grants.

Use an authenticated installation administrator already named by trusted policy.
The target's complete issuer, subject and kind must be known to that policy.
The examples use the existing fixed static-development issuer; they do not add
credential provisioning or a configurable issuer. Credentials remain in the
client profile's private files and are not included in payloads.

## Create a workspace, then grant ordinary access

`POST /administration/workspaces` (`command.workspace-administration.create`):

```json
{"workspace_id":"workspace-b","name":"Workspace B","idempotency_key":"create-workspace-b"}
```

Workspace creation does not automatically grant ordinary workspace permissions
or runtime management. Grant only the needed ordinary scopes through
`POST /workspaces/workspace-b/permissions/grant`
(`command.workspace-permission.grant`):

```json
{
  "target":{"issuer":"urn:control-plane-kit:static-development","subject_id":"operator","kind":"operator"},
  "scopes":["instance:workspace:read"],
  "expected_revision":0,
  "idempotency_key":"grant-workspace-b-read"
}
```

Here revision zero applies only to a new permission record. For an existing
record, inspect it first and use its observed revision. A conflicting response
requires inspection; do not silently substitute another revision or key.

Read the record using the existing public client transport:

```python
record = transport.call(
    "read.workspace-permission",
    path_parameters={"workspace_id": "workspace-b"},
    payload={"target": {
        "issuer": "urn:control-plane-kit:static-development",
        "subject_id": "operator", "kind": "operator",
    }},
    credential_role="operator",
)
```

`transport` is a `PublicHttpTransport` built from the reviewed administrator's
existing `ClientProfile`. A profile credential-role label selects a private
credential file; it does not make that identity an administrator. The client
encodes the target JSON and preserves spaces and literal plus signs. The target
principal can use its existing credential for newly permitted ordinary workspace
requests without replacing the verifier or restarting CPK.

## Grant management separately

An active registered runtime and ordinary workspace access do not imply
management eligibility. After the separate authorized runtime registration,
use its returned registration ID, the exact runtime/authority coordinates and
an already installed capability in
`POST /workspaces/workspace-b/runtime-management/grant`
(`command.managed-runtime-access.grant`):

```json
{
  "runtime_id":"docker",
  "authority_ref":"managed-local",
  "registration_id":"<returned-registration-id>",
  "capability_id":"installed-docker-management",
  "expected_revision":0,
  "idempotency_key":"grant-workspace-b-management"
}
```

The registration placeholder must be replaced with authoritative returned data;
do not invent it. Revision zero again assumes a new assignment. Inspect an
existing assignment with `read.managed-runtime-assignment`, passing raw
`runtime_id` and `authority_ref` strings in the client's query payload.
Neither the grant nor public input supplies a socket, endpoint or client object.
The server binds the installed capability to its trusted local transport policy.

## Revoke each authority explicitly

To revoke ordinary access, post the same complete `target`, the exact scopes to
remove, the latest permission-record `expected_revision`, and a distinct
`idempotency_key` to `/workspaces/workspace-b/permissions/revoke`
(`command.workspace-permission.revoke`).

To revoke management, post `runtime_id`, `authority_ref`, the latest assignment
`expected_revision`, and a distinct `idempotency_key` to
`/workspaces/workspace-b/runtime-management/revoke`
(`command.managed-runtime-access.revoke`). Read back each affected owner record.
These are separate durable changes; neither replaces the other.

Revocation denies later fresh admissions. An already admitted bounded attempt
may finish and record its result; revocation is not cancellation. Restart does
not restore stale credential grants or revoked management assignments.

HTTP and MCP share the same Operations owners. MCP command names are
`create_workspace_as_administrator`, `grant_workspace_permissions`,
`revoke_workspace_permissions`, `grant_managed_runtime_access`, and
`revoke_managed_runtime_access`. Supply `workspace_id` in MCP arguments for the
workspace-scoped commands. This example introduces no new CLI subcommands.
