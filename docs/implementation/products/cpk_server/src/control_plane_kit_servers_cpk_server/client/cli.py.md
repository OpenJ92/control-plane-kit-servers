#371 renders only the retained safe HTTP status and closed stage/reason/acceptance in human output. JSON includes the optional result fields unchanged. No raw error text, response headers or credentials are displayed. Source review and the complete normal Docker gate passed at fdacc9405138e9b25b4c2928a3d5c13b9a7ecdae; required CI remains pending.

The gate passed all 1,260 product tests plus 26 test-support tests, compilation,
clean import and the normal smoke/cleanup stages. See [the complete result and
scoped cleanup limits](https://github.com/OpenJ92/control-plane-kit-servers/issues/371#issuecomment-6598347612).
Earlier pending-validation statements below describe historical slices.

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
