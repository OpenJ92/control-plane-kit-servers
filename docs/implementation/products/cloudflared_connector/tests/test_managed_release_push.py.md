# Same-push anchor tests

Synthetic owner tests cover exact source/candidate/destination/whole-manifest
receipt binding; duplicate, malformed, wrong-tag, nonterminal, control-byte,
oversize and nonzero-exit refusals; unsupported image-store/engine profiles;
no-follow ancestor/file reads and concurrent file change detection. Existing
producer command doubles invoke the real parser/profile CLI without registry
access and refuse unsupported producer paths before push. Existing projector
fixtures cover altered layer descriptors despite equal config and internally
consistent remote/package identities, substituted receipt/transcript/daemon/
candidate, independent top and child sizes, raw-byte tamper, and config mismatch.
The new contract intentionally requires push.exit0; do not restore the historical
missing-exit publication allowance. No live release or historical-cause claim.
