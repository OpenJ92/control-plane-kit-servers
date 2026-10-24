Source: [cloudflared_connection_witness.sh](../../../scripts/cloudflared_connection_witness.sh).

Called by the normal owning test.sh after existing product witnesses. Builds the
source connector image with a unique run label, captures its actual image Config,
then runs the packaged witness under the product's numeric UID with network none.
It creates no tunnel or provider request. Synthetic token bytes exist only in
the disposable fixture container. The reader receives an unreadable token-file
reference to demonstrate independence from intentional token access.

The fixture overrides the process entrypoint and disables periodic healthchecks
to control the exact local-response client. The original image's PID1 entrypoint,
stop signal, UID and healthcheck command/bounds are checked from image Config;
these are configuration evidence, not a real tunnel shutdown/connection proof.

Cleanup validates immutable recorded container identity, run label, image ID and
tag association before removing only those owned resources. Failure preserves
records for diagnosis. There is no prune, unrelated image removal or daemon
access inside the product container. Normal final residue audit still runs.
