Source: [docker_witness_daemon.sh](../../../scripts/docker_witness_daemon.sh).

This shell preflight belongs to the existing CPK image-update/reintroduction
witness. It accepts a selected Docker context with an absolute local Unix
endpoint, including Linux and Desktop. It refuses nonempty DOCKER_HOST,
DOCKER_TLS, DOCKER_TLS_VERIFY or DOCKER_CERT_PATH rather than resolving mixed
selection modes. It fixes the selected context for subsequent CLI calls and
requires a nonempty daemon ID. CLI failure propagates; no fallback or retry.

The helper neither creates resources nor changes the daemon-side socket mount.
The existing controller independently checks mounted daemon ID, its own image
and run label before managed workload effects. Tests exercise this admission
with a CLI double inside the normal Docker package suite; they do not establish
real socket identity. The complete owning gate supplies that evidence.
