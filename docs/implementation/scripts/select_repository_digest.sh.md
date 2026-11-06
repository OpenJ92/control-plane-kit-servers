Source: [select_repository_digest.sh](../../../scripts/select_repository_digest.sh).

Please update alongside its source file.

Pure metadata helper used by the Hello producer. It reads RepoDigest
lines from stdin and selects exactly one canonical lowercase SHA256 entry for
the explicit requested repository. Separate mandatory prefix/length checks fail
closed under set-e. There is no Docker, network, registry, credential or cleanup
effect. Existing owning package tests execute the actual shell helper with data
for valid/reordered, absent, wrong repository, ambiguous and malformed cases.
The publisher separately correlates the selected record with its captured image
ID; neither this helper nor its tests prove a pushed/pulled artifact.
