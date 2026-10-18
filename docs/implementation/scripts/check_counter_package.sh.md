Source: [check_counter_package.sh](../../../scripts/check_counter_package.sh).

This read-only provider guard requires exact private package13950177 and its
Servers repository association. The producer's existing write-scoped workflow
token and preload's existing read-scoped token are supplied as GH_TOKEN only to
their respective steps; Docker login alone does not authenticate gh. Actual
endpoint access is an execution prerequisite, not inferred from local credentials.

`read` verifies the package before digest preload. `before-push` also verifies
the dedicated tag is absent across all version pages. `published` correlates one
actual digest/tag version and reports its complete tag set. Failed requests or
pagination, malformed records, false predicates and ambiguous matches refuse.
Capture gh output before parsing so downstream jq cannot hide an upstream error.

The guard never changes access, visibility, tags or packages, and never retries.
Pre/post checks do not make push transactional. The recorded complete tag set
is required context for any separately approved later cleanup: never delete the
shared package or a version with unrelated tags. Metadata is bounded to the
required fields in output; credentials are never printed.
