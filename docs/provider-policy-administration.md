# Provider-policy administration

The CPK server exposes the accepted Operations administration service through
its existing authenticated HTTP and MCP surfaces. It is disabled by default.
Ordinary workspace administration and secret-use permissions grant no access to
this family. An installer must admit the full principal identity and logical
provider independently.

Set `CPK_PROVIDER_POLICY_AUTHORITY=secrets-v1` and
`CPK_PROVIDER_POLICY_AUTHORITY_CONFIGURATION_FILE` to an absolute regular file.
Both settings are required together. Configuration is read once (at most 1 MiB,
1,024 admissions/bindings); symlinks, duplicate/extra fields and malformed input
fail startup with a fixed error. Parent directories are installer-trusted.
Credential values never appear in this file. Example metadata:

```json
{
  "schema": "cpk-server.provider-policy-authority.v1",
  "installation_id": "installation-a",
  "admissions": [{
    "identity": {"issuer": "issuer-a", "subject_id": "administrator-a", "kind": "operator"},
    "binding_id": "policy-binding-a"
  }],
  "bindings": [{
    "binding_id": "policy-binding-a",
    "logical_provider_id": "logical-a",
    "provider_id": "provider-a",
    "endpoint_reference": "policy-endpoint-a",
    "base_url": "https://provider.example.invalid",
    "credential_reference": "secret://provider/independent-policy-admin",
    "credential_file": "/run/secrets/provider-policy-admin"
  }]
}
```

The credential file belongs to the independent provider-policy administrator.
Do not reuse the ordinary secret-use credential. Assembly validates metadata but
does not open that credential, construct its client, discover a target, or call
the provider. Operations admits the verified principal/provider first; only then
does the exact full binding select the fixed interpreter client. Missing bindings
fail closed. Multiple principals can name the same binding. If workspace authority
is also configured, both policies must name the same installation; their grants
remain independent.

Configuration changes require a new application instance and an installer-managed
traffic cutover. **A binding ID must remain associated with its original target
and credential identity. Use a new binding ID when retargeting either.** Operations
compares historical binding triples and rejects replaced bindings. It does not
retain old endpoint/file snapshots and cannot detect a target silently changed
under the same binding triple. There is no automatic rebinding or retry here.

HTTP paths start with `/administration/provider-policies/{logical_provider_id}`:

| Method/path suffix | MCP route name | Purpose |
| --- | --- | --- |
| POST `/grants` | `command.provider-policy.grant` | Record and dispatch one grant |
| POST `/grants/{grant_id}/revoke` | `command.provider-policy.revoke` | Record and dispatch one revoke |
| POST `/commands/{command_id}/reconcile` | `command.provider-policy.reconcile` | Read back the original command result |
| GET `/commands/{command_id}` | `read.provider-policy-command` | Read the local command record |
| GET `/grants/{grant_id}` | `read.provider-policy-grant` | Read the current provider grant |
| GET `/grants` | `read.provider-policy-grants` | List current active grants |

Grant/revoke bodies contain only `coordinate` (subject, workspace_id, action,
intent), `expected_revision`, and `idempotency_key`. Reconcile has an empty object
body. MCP arguments include the path parameters alongside those same fields.
HTTP detail/command reads accept no query fields. List accepts percent-encoded
string filters `subject`, `workspace_id`, `action`, `intent_mode`, `intent`, and
`after_grant_id`, plus integer `limit`; omit optional filters instead of sending
JSON null. Owner defaults are limit 100 and intent_mode `any`. The accepted owner
validates filter combinations and page limits. Workspace filters do not resolve
workspace authority. Unknown/duplicate query fields are rejected.

Canonical responses are bounded to 64 KiB (grant pages 1 MiB); Operations bounds
command descriptors to 60 KiB and reports omitted observations. It owns command
transactions, single-dispatch claims, uncertainty and history. Current grant
reads create no local mirror. This source composition does not establish live
provider/process acceptance, image publication or deployment.
