# `client/cli.py`

Receiver authoring flags are valid only with a graph file. Introductions name an
exact node/socket/artifact/path. Pending continuation requires a draft, exact
head, and at least one explicitly selected scope. Gateway targets must attach to
one declared complete-replacement group; duplicate groups, duplicate targets,
unattached targets, and malformed combinations refuse locally.

The CLI constructs typed authoring values. It does not accept receiver JSON,
route JSON, credentials, private keys, saved-revision relabeling, or implicit
last-target removal.
