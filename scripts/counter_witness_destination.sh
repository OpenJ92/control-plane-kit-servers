#!/bin/sh
# Pure, closed destination selection; no provider or credential access.
set -eu
[ "$#" = 3 ]
[ "$1" = openj92 ]
[ "$2" = control-plane-kit-servers ]
TAG="$3"
SUFFIX="${TAG#counter-witness-264-}"
[ "$TAG" = "counter-witness-264-$SUFFIX" ]
[ "${#SUFFIX}" -ge 7 ]
[ "${#SUFFIX}" -le 40 ]
case "$SUFFIX" in *[!0-9a-f]*) exit 1 ;; esac
printf 'ghcr.io/openj92/control-plane-kit-servers/cpk-server:%s\n' "$TAG"
