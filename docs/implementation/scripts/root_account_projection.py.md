Source: [root_account_projection.py](../../../scripts/root_account_projection.py).

#347 diagnostic source. The original seven synthetic laws passed at ac144857;
the subsequent acquisition-admission additions require their own source review
and owning gate. It verifies one CPK immutable
reference, original index/platform manifest, configuration and ordered layers
against a separately prepared OCI layout. Duplicate JSON keys, ambiguous platform
selection, unsupported media/foreign URLs, invalid sizes, platform/user/revision
mismatch, normalization drift, blob corruption and unequal layer/diff-ID counts
refuse before unpack. Original and OCI-normalized manifest identities stay
distinct. Actual referenced bytes are hashed, with a 2 GiB compressed-layer sum
ceiling. This is not a bound on the earlier registry acquisition operation.

The acquisition entrypoint now reuses this owner for two metadata-only commands:
`--select REFERENCE` binds original bytes and selects exactly one manifest;
`--admit REFERENCE` validates original/platform correspondence, closed descriptors,
foreign-content refusal and compressed sum before blob copy. Both use the same
fixed read-only /input mount and bounded, redacted CLI. They do not unpack, read
accounts, call the network or claim account evidence. The final layout verifier
repeats that admission and verifies actual copied bytes before umoci.

The verified umoci0.6.0 binary owns unpacking, whiteouts, links and diff-ID checks.
The published amd64 release asset's SHA256 is pinned to
`b51c267ec394499e42c6fde47f240b7b7dba57ea49df0b5acd304378b82a3b71`, as reported
by the official release API; no binary was acquired during source preparation.
The helper does not execute image code. Tool output is discarded and nonzero or
timed-out unpack cannot produce a seal. Each invocation creates its own fresh
bundle directory; no supplied arbitrary account path or success flag is accepted.

Final account reads use directory descriptors and no-follow opens through
rootfs/etc. Post-open checks require regular single-link files no larger than
64 KiB. The selected username/UID and primary group must be unambiguous; all group
membership entries are scanned to derive the supplementary GID set. Host NSS,
process groups and rootless mapped ownership are not expected-value sources.
Only hashes/numeric accounts and bounded provenance are returned; raw files,
configuration/environment and exception content are never printed by the CLI.

The fixed mounts and disk/memory/wall bounds belong to the separately reviewed
invocation. Data stays on its owned tmpfs until container removal. A successful
helper result is a candidate, not accepted account evidence or runtime identity.
Independent review must bind the actual producer, source/controller/tool records
and published digest before installing a new baseline row.
