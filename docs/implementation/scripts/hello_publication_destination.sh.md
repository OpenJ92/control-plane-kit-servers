Please update alongside [hello_publication_destination.sh](../../../scripts/hello_publication_destination.sh).

Pure closed destination guard, called by the publisher before metadata reads,
Docker builds or pushes. Every owner/package/source/tag requirement is an
independent mandatory shell command. Do not combine owner and package checks
with `&&`: POSIX errexit exempts a failed non-final AND-list command. Exact valid
inputs produce only the fixed Hello repository and full-source tag. Invalid
inputs fail without output. Tests exercise this actual shell helper, with no
simulated gh/Docker success or registry effects.
