Source: [docker_image_update_provider.py](../../../../../products/cpk_server/tests/docker_image_update_provider.py).

The authored public receiver configuration uses the Secrets owner's required
0444 mode. Master key, provider token and credentials remain 0400; their enclosing
directory stays 0700. Applying the private-file mode to the public control file
caused the first live startup to fail admission before any managed topology ran.

The pinned Secrets application runs as an exact owned uvicorn child on loopback.
Private environment/files exist before import. Its encrypted SQLite store and
credentials are scoped to this unique fixture workspace, with public HTTP
write/resolve through ControlPlaneKitSecretsClient. CPK's existing provider-mode
composition supplies the real authorized resolver to health/runtime ports.
Secrets never enter command arguments or process output; stdout/stderr are
discarded. Bounded readiness and exact terminate/wait/kill teardown precede
private temporary-file disposal. No user/provider credential is used.

The generated-secrets endpoint and bootstrap credential now map to the same
private provider, with the connector's exact cloudflare.tunnel-token intent.
SyntheticIngressAllocation keeps external tunnel/DNS identities synthetic but
delegates storage/revocation of a random non-Cloudflare token to the existing
ControlPlaneKitSecretsCustodian. Only the actual public writer's receipt enters
the allocation; a failed write admits no synthetic allocation. Exact workspace,
endpoint, bootstrap reference, intent and reference prefix guard this fixture
boundary. No custody lifecycle, retry, protocol or provider state is reimplemented.
#253 seeds the distinct workload-overlap private material at its matching
`secret://health-secrets/keys/workload-overlap` reference using the same public
write/resolve path. The existing provider endpoint, bootstrap credential and
workload-health intent remain unchanged; the signing intent grant list is not
expanded. The overlap is never activated or selected for signing. Existing
private fixture process/store teardown disposes of this additional custody.
