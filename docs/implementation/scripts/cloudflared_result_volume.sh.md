# Managed witness result volume

This product-specific shell entry serves the existing normal/contents and
candidate owners. It acquires one fresh default local volume, records the
planned name before creation and the verified run/project/creation association
afterward. It never adopts a pre-existing volume, retries an uncertain create,
uses driver options, or exposes a daemon host path to the helper.

Removal requires the successful acquisition record, the controller's matching
empty-volume marker, current matching association and zero container references.
It removes only that volume without force and verifies absence. A missing marker,
unknown result, mismatched identity, active reference or ambiguous effect stops
and retains evidence. Volume names/creation timestamps are supporting association,
not immutable IDs; the fresh run namespace has no competing writer.

Owners invoke this as a separate shell process, so its fail-fast checks remain
effective even when the caller captures cleanup failure in a conditional. It is
not a standalone release command, recovery framework, or authorization to prune.
