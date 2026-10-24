#!/bin/sh
# Pure, closed destination selection. No Docker, GitHub or credential access.
set -eu
OWNER="${1:?owner required}"
PACKAGE="${2:?package required}"
TAG="${3:?tag required}"
SOURCE="${4:?source required}"
# Keep each refusal mandatory: an AND-list's non-final false command is exempt
# from POSIX errexit, so it must not guard a subsequent consequential command.
[ "$OWNER" = openj92 ]
[ "$PACKAGE" = control-plane-kit-servers ]
[ "${#SOURCE}" = 40 ]
case "$SOURCE" in *[!0-9a-f]*) exit 1 ;; esac
[ "$TAG" = "hello-271-$SOURCE" ]
printf 'ghcr.io/openj92/control-plane-kit-servers/hello-server:%s\n' "$TAG"
