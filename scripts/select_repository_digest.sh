#!/bin/sh
# Pure producer metadata selection: repository argument, RepoDigest lines on stdin.
set -eu
REPOSITORY="${1:?exact repository is required}"
REFERENCE="$(awk -v repository="$REPOSITORY@" 'index($0, repository) == 1 {print}')"
DIGEST="${REFERENCE#"$REPOSITORY"@sha256:}"
# Separate mandatory tests reject absent or multiple matches under set -e.
[ "$REFERENCE" = "$REPOSITORY@sha256:$DIGEST" ]
[ "${#DIGEST}" = 64 ]
case "$DIGEST" in *[!0-9a-f]*) exit 1 ;; esac
printf '%s\n' "$REFERENCE"
