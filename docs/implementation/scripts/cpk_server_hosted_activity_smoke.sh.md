Source: [scripts/cpk_server_hosted_activity_smoke.sh](../../../scripts/cpk_server_hosted_activity_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This legacy harness chooses a server descriptor/image, optionally builds a
controller, generates gateway signing material, starts local Postgres and a
socket-mounted CPK process, then dispatches scenarios through the Python
controller. Host Python and the repository working directory are required.
Only the exact public-gateway-ingress scenario defaults to the Docker/Cloudflare
descriptor. authenticated-gateway-private instead builds a fixed local tag.

The environment is incompatible with current server bootstrap: it always pairs
Ed25519 signing with local-development material, whereas the server requires
provider-backed resolution. Its credential-present branch also sets explicitly
rejected legacy Docker-config bootstrap. Cloudflare mode likewise requires
provider material. These are source-derived inconsistencies, not claims about
every historical published digest.

Effects precede that server rejection: builds/pulls, key generation, containers
and credential-file staging. In ingress modes the configured environment file
is sourced as shell code. Tokens/private material pass through environments;
socket mounts grant daemon access. Static development credentials and fixed
workspace grants are harness configuration, not production custody.

Cleanup removes infrastructure by captured IDs/name and suppresses Docker errors.
Activity cleanup scans five fixed workspace label values across the daemon,
not a unique run identity, so it can select another matching run's resources.
KEEP_ON_FAILURE disables the cleanup trap and retains resources/material;
otherwise failure prints a log tail without general redaction. The final echo
and residue audit do not supply a complete durable ledger or compensation proof.

Related source: [process admission](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md),
[hosted controller](../../../scripts/cpk_server_hosted_activity.py),
[residue audit](docker_residue_audit.sh.md).
