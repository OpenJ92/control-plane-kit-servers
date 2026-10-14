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
