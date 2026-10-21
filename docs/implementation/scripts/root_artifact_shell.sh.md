Source: [root_artifact_shell.sh](../../../scripts/root_artifact_shell.sh).

This shared boundary has two product consumers and their gate/preloader. Sourcing
performs no effects. Selection uses no host Python and refuses invalid tuples
before Docker. Admission inspects the cached reference before starting the
existing controller; no login, pull, rebuild or registry credential mount occurs.

The controller runs network-none/read-only/capability-dropped without a socket.
It uses the invoking numeric UID/GID so it can read the 0600 evidence files without
DAC-override capability or a permission broadening.
It validates metadata and records execution ID. Product startup uses that ID with
pull disabled. Actual container Image and current cache binding must match.

Dependency probes run inside the actual product. Producer status is saved
independently of the bounded consumer; success and JSON of at most 65536 bytes are
both required. Evidence/status files join the existing fixture cleanup list.
Raw metadata/tracebacks are not printed, only validated public provenance fields.

Final artifact PASS follows the owner's cleanup/audit boundary. It is ABI evidence,
not producer review, registry privacy or live #225 acceptance. Gate and producer
revisions are recorded separately.
