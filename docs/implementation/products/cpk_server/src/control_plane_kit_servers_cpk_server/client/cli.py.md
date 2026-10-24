# `client/cli.py`

Receiver authoring flags are valid only with a graph file. Introductions name an
exact node/socket/artifact/path. Pending continuation requires a draft, exact
head, and at least one explicitly selected scope. Gateway targets must attach to
one declared complete-replacement group; duplicate groups, duplicate targets,
unattached targets, and malformed combinations refuse locally.

The CLI constructs typed authoring values. It does not accept receiver JSON,
route JSON, credentials, private keys, saved-revision relabeling, or implicit
last-target removal.

`--refresh-receiver-verifiers NODE SOCKET` builds a repeatable tuple of explicit
current scopes on `AuthoredDesiredGraph`. The existing graph-file-only exclusion
also covers this flag. Typed input validation rejects duplicate scopes and
overlap with introduction/pending intent. Repeatability is authoring syntax;
Core/Operations remain authoritative for supported plan compositions.

`--update-receiver-declaration NODE SOCKET` selects `declaration_updates` on
the same graph-file-only input. Duplicates and overlap with refresh,
introduction or pending continuation refuse. The graph supplies the desired
registered successor and declaration; separate complete gateway route flags
supply explicit aliases/origins. No registration, approval or apply is implied.
