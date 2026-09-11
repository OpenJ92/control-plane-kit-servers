Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This adapter extracts exactly one case-insensitive Authorization header from
the supplied mapping, requires a Bearer scheme and nonempty whitespace-free
ASCII token of at most 4096 bytes, and passes those bytes to the configured
Core CredentialVerifier. Duplicate entries visible through items(), including
Starlette raw-header duplicates, are rejected. The outer HTTP adapter owns
preserving duplicates in that representation.

Verifier exceptions and non-principal returns become a new categorical
CredentialAuthenticationError after the catch, avoiding retention of that
verifier exception. The non-ASCII extraction path separately chains its
UnicodeEncodeError, so the guarantee is not universal exception-chain
redaction. Rebinding the local credential to empty bytes is not memory
zeroization and does not erase the caller's headers or a verifier's storage.

Development verifiers admit bounded ASCII byte credentials and explicit Core
principals, reject duplicate credentials and limit the multi-principal tuple to
16 entries. Individual comparisons use hmac.compare_digest, but the search
returns at the first match. Credential fields are hidden from repr; principal
identity and workspace grants remain visible. The single-operator wrapper
constructs a fixed development operator identity with the supplied grants,
rather than deriving authority from a request payload.

The verifier exchanges a credential for identity; selected Core
AuthenticatedPrincipal/WorkspaceGrant values and Operations authorization own
workspace and route permissions. This module does not authorize deployment,
refresh grants, provide durable sessions or implement a production identity
provider. Review these imports at the actual package pin.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/tests/test_http_mcp_boundaries.py](../../../../../../products/cpk_server/tests/test_http_mcp_boundaries.py), [products/cpk_server/tests/test_installation_control_auth.py](../../../../../../products/cpk_server/tests/test_installation_control_auth.py), [pyproject.toml](../../../../../../pyproject.toml).
