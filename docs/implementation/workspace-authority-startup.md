# Dynamic workspace authority process input

This is source configuration documentation for Servers #341, not an installation
or deployment instruction. The supported bootstrap v2 authoring/policy-delivery
handoff remains unresolved; the existing topology artifact helper is v1-only.

An installer selects `CPK_WORKSPACE_AUTHORITY=dynamic-v1` with an absolute
`CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE` pointing to a trusted regular file:

```json
{
  "schema": "cpk-server.workspace-authority.v1",
  "installation_id": "example-installation",
  "administrators": [
    {"issuer": "urn:control-plane-kit:static-development", "subject_id": "installer", "kind": "operator"}
  ],
  "known_identities": [
    {"issuer": "urn:control-plane-kit:static-development", "subject_id": "installer", "kind": "operator"},
    {"issuer": "urn:control-plane-kit:static-development", "subject_id": "operator", "kind": "operator"}
  ],
  "capabilities": ["installed-docker-management"]
}
```

The existing credential verifier must authenticate those exact full identities.
No credential belongs in this policy file. In validated dynamic mode, existing
single/multi credential inputs may contain explicit empty workspace grant maps;
they may not omit or malform the field. Current permissions and management
assignments come from Operations. Static mode retains its prior grant requirements.
An existing owner initialization receipt is required; startup does not seed or
repair permissions. This file contains no per-workspace assignment list.

For dynamic managed health, select `CPK_MANAGED_HEALTH=docker-unix-v2` and the
existing `CPK_MANAGED_HEALTH_CONFIGURATION_FILE`. Its closed schema is
`cpk-server.managed-health.v2`: retain the existing `docker`, canonical
`gateway_documents` and canonical `native_product_document` values, replacing
v1 `scopes` with `capability_ids`. The IDs must match the complete workspace-policy
catalogue and share the one installed local Docker policy. The file has no UoW,
client object, grant or credential. Dynamic workspace authority without managed
health is supported. Mixed modes/catalogues and mislabeled schemas refuse.

These are immutable installer inputs, bounded independently from durable
workspace population. Their parent directories are trusted; final symlinks and
nonregular/oversized files are refused. Configuration changes need a restart;
routine create/grant/revoke operations use the existing authenticated public
commands and do not edit these files or restart the process.
