Source: [counter_witness_destination.sh](../../../scripts/counter_witness_destination.sh).

This pure shell transform accepts one fixed owner/package pair and dedicated
counter tag vocabulary, and returns the exact existing private storage location.
It rejects overrides, production tags and malformed source prefixes without
output. The producer separately binds that prefix to its actual checkout and
reads current provider visibility/access. Neither this helper nor its tests
prove that GitHub is private or writable.
