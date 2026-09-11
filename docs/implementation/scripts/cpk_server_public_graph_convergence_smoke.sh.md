Source: [scripts/cpk_server_public_graph_convergence_smoke.sh](../../../scripts/cpk_server_public_graph_convergence_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

Disposable, persistent-bootstrap and attach modes run under umask077.
Controllers use public APIs without Docker socket, database URLs or provider
credentials; CPK owns the socket. Bootstrap helpers are socket-free/network-none.
That separation does not make the host shell or CPK unprivileged.

Persistent bootstrap requires fresh state, explicit approval, exact cached image
IDs, existing provider credentials and an opaque token reference. It creates a
labelled network/volume, records returned IDs and volume creation time, writes
private bootstrap and starts Postgres/CPK. The ready marker follows CPK launch,
not verified CPK/external connectivity. Postgres uses pg_isready here, not the
authenticated SQL witness in image_smoke. Partial failure has no rollback trap.

Attach checks recorded files, images, network/volume markers, running/health
state, mounts and network attachment before a new public controller. It neither
recreates/restarts nor disposes of the installation. Successful attach removes
only its controller; failure retains it and evidence. These checks are not a
complete engine-identity, credential-custody or race-proof resource attestation.

Disposable mode requires transition/destructive consent and cached-image syntax,
rejects registry configuration and creates fresh bootstrap/evidence directories.
Postgres data is tmpfs. Only successful controller completion with a present
report triggers infrastructure cleanup by returned container/network IDs;
failure retains infrastructure/history. Cleanup failure can leave partial
disposal. Return codes, not independent absence queries, establish its result.

All Docker runs use pull=never; there is no registry pull or source-image parity
verification. Disposable Postgres still uses a tag, unlike persistent exact-ID
checks. docker wait and controller-log output have no global timeout or general
byte/redaction guard. This effectful fixture is not permission to run another
held acceptance scenario.

Related source: [controller](cpk_server_public_graph_convergence.py.md),
[launcher assertions](../../../products/cpk_server/tests/test_image_bootstrap.py).
