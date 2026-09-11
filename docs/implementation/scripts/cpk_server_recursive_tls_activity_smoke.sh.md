Source: [scripts/cpk_server_recursive_tls_activity_smoke.sh](../../../scripts/cpk_server_recursive_tls_activity_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This legacy launcher builds/selects controllers and images, starts local
Postgres plus privileged Docker-in-Docker, waits for its TLS version query and
copies client CA/certificate/key files to mode0400 temporary files. It embeds
those values and optional Docker registry credentials in nested local secret
JSON passed to the parent; the controller also mounts the host Docker socket.

The parent is configured only with the old auth-configured flag, not a verifier,
and optional legacy Docker-config settings. Current main rejects missing verifier
configuration and current bootstrap rejects those legacy fields. Existing
historical-image behavior is not audited by reading this fixture.

Cleanup removes captured infrastructure and scans fixed parent/child workspace
labels on the host daemon, suppressing failures. It also removes certificate and
registry staging directories. These labels are not unique run ownership;
partial cleanup and anonymous DinD storage are not explicitly accounted for.
Removing the DinD container is not independent verification of every remote
resource's absence.

Family-size bounds live in the controller. Postgres readiness uses local psql;
DinD TLS readiness proves its selected version call, not later child authority
admission or grandchild health. Failure tails selected containers/DinD and
matching-workspace logs without general byte/redaction bounds. No separate
opt-in, global deadline or durable compensation ledger exists in this shell.

Related source: [controller](cpk_server_recursive_tls_activity.py.md),
[process admission](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md),
[residue audit](docker_residue_audit.sh.md).
