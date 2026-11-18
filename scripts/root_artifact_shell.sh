# Closed shell boundary shared only by the two current-root smoke owners/gate.
# Sourcing this file performs no Docker or filesystem effects.
root_artifact_invalid() {
  echo 'current root artifact input is invalid' >&2
  return 2
}

root_artifact_reference() {
  case "$2" in "ghcr.io/openj92/control-plane-kit-servers/$1@sha256:"*) ;;
    *) return 1 ;; esac
  root_digest="${2#*@sha256:}"
  [ "${#root_digest}" = 64 ] || return 1
  case "$root_digest" in *[!0-9a-f]*) return 1 ;; esac
}

root_artifact_selection() {
  case "${CPK_ROOT_ARTIFACT_MODE-source-built}" in
    source-built)
      [ -z "${CPK_ROOT_CPK_IMAGE:-}${CPK_ROOT_SECRETS_IMAGE:-}${CPK_ROOT_SOURCE_REVISION:-}" ] || root_artifact_invalid
      ;;
    published-digest)
      root_artifact_reference cpk-server "${CPK_ROOT_CPK_IMAGE:-}" || { root_artifact_invalid; return 2; }
      root_artifact_reference secrets-server "${CPK_ROOT_SECRETS_IMAGE:-}" || { root_artifact_invalid; return 2; }
      root_source="${CPK_ROOT_SOURCE_REVISION:-}"
      [ "${#root_source}" = 40 ] || { root_artifact_invalid; return 2; }
      case "$root_source" in *[!0-9a-f]*) root_artifact_invalid; return 2 ;; esac
      ;;
    *) root_artifact_invalid; return 2 ;;
  esac
}

root_artifact_inspection() {
  docker image inspect "$1" --format '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},"Os":{{json .Os}},"Architecture":{{json .Architecture}},"Config":{"User":{{json .Config.User}},"Labels":{"org.opencontainers.image.revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}}}}}'
}

root_artifact_checker() {
  docker run --pull never --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user "$(id -u):$(id -g)" -i \
    -e "CPK_ROOT_ARTIFACT_MODE=$CPK_ROOT_ARTIFACT_MODE" \
    -e "CPK_ROOT_CPK_IMAGE=$CPK_ROOT_CPK_IMAGE" \
    -e "CPK_ROOT_SECRETS_IMAGE=$CPK_ROOT_SECRETS_IMAGE" \
    -e "CPK_ROOT_SOURCE_REVISION=$CPK_ROOT_SOURCE_REVISION" \
    "$ROOT_ARTIFACT_CONTROLLER" python scripts/root_artifact_inputs.py "$@"
}

root_artifact_admit() {
  root_artifact_selection || return 2
  [ "${CPK_ROOT_ARTIFACT_MODE:-}" = published-digest ] || { root_artifact_invalid; return 2; }
  ROOT_ARTIFACT_ROLE="$1"
  ROOT_ARTIFACT_REFERENCE="$2"
  case "$1" in
    cpk-server) [ "$2" = "$CPK_ROOT_CPK_IMAGE" ] || { root_artifact_invalid; return 2; } ;;
    secrets-server) [ "$2" = "$CPK_ROOT_SECRETS_IMAGE" ] || { root_artifact_invalid; return 2; } ;;
    *) root_artifact_invalid; return 2 ;;
  esac
  # Missing cache refuses before controller startup and never pulls/rebuilds.
  root_attrs="$(root_artifact_inspection "$2" 2>/dev/null)" || { root_artifact_invalid; return 2; }
  ROOT_ARTIFACT_CONTROLLER="$(docker image inspect "$3" --format '{{.Id}}')" || return 1
  ROOT_ARTIFACT_IMAGE_ID="$(printf '%s' "$root_attrs" | root_artifact_checker admit \
    "$1" "$2" "$CPK_ROOT_SOURCE_REVISION")" || return 1
}

root_artifact_verify_container() {
  root_container="$1"
  root_records="$2"
  root_attrs="$(root_artifact_inspection "$ROOT_ARTIFACT_REFERENCE" 2>/dev/null)" || { root_artifact_invalid; return 2; }
  printf '%s' "$root_attrs" | root_artifact_checker admit "$ROOT_ARTIFACT_ROLE" \
    "$ROOT_ARTIFACT_REFERENCE" "$CPK_ROOT_SOURCE_REVISION" "$ROOT_ARTIFACT_IMAGE_ID" >/dev/null || return 1
  root_observed="$(docker inspect "$root_container" --format '{{.Image}}')" || return 1
  root_artifact_checker execution "$ROOT_ARTIFACT_IMAGE_ID" "$root_observed" </dev/null || return 1
  (umask 077; : > "$root_records/artifact-pid1.status"; : > "$root_records/artifact-pid1.exit") || return 1
  # Observe the running server (PID 1), not the newly exec'd probe's user.
  if (
    set +e
    docker exec "$root_container" python -B -c \
      'import sys; f=open("/proc/1/status","rb"); sys.stdout.buffer.write(f.read(65537))' 2>/dev/null
    root_probe_status=$?
    printf '%s\n' "$root_probe_status" > "$root_records/artifact-pid1.exit"
  ) | head -c 65537 > "$root_records/artifact-pid1.status"; then :; else return 1; fi
  [ "$(cat "$root_records/artifact-pid1.exit")" = 0 ] || { root_artifact_invalid; return 2; }
  [ "$(wc -c < "$root_records/artifact-pid1.status")" -le 65536 ] || { root_artifact_invalid; return 2; }
  docker run --pull never --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$root_records,target=/artifact-evidence,readonly" \
    "$ROOT_ARTIFACT_CONTROLLER" python scripts/root_artifact_inputs.py process-uid \
    "$ROOT_ARTIFACT_ROLE" /artifact-evidence/artifact-pid1.status || return 1
  case "$ROOT_ARTIFACT_ROLE" in
    cpk-server) set -- control-plane-kit-core control-plane-kit-operations control-plane-kit-server-sdk control-plane-kit-interpreters ;;
    secrets-server) set -- control-plane-kit-core control-plane-kit-server-sdk control-plane-kit-secrets ;;
    *) root_artifact_invalid; return 2 ;;
  esac
  (umask 077; : > "$root_records/artifact-provenance.json"; : > "$root_records/artifact-provenance.status") || return 1
  # Preserve the producer's status independently from the bounded consumer.
  if (
    set +e
    docker exec "$root_container" python -B -c \
      'import importlib.metadata as m,json,sys; print(json.dumps({n:json.loads(m.distribution(n).read_text("direct_url.json")) for n in sys.argv[1:]},sort_keys=True))' \
      "$@" 2>/dev/null
    root_probe_status=$?
    printf '%s\n' "$root_probe_status" > "$root_records/artifact-provenance.status"
  ) | head -c 65537 > "$root_records/artifact-provenance.json"; then :; else return 1; fi
  [ "$(cat "$root_records/artifact-provenance.status")" = 0 ] || { root_artifact_invalid; return 2; }
  [ "$(wc -c < "$root_records/artifact-provenance.json")" -le 65536 ] || { root_artifact_invalid; return 2; }
  docker run --pull never --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$root_records,target=/artifact-evidence,readonly" \
    "$ROOT_ARTIFACT_CONTROLLER" python scripts/root_artifact_inputs.py provenance \
    "$ROOT_ARTIFACT_ROLE" /artifact-evidence/artifact-provenance.json
}

root_artifact_pass() {
  printf 'current root artifact ABI passed role=%s reference=%s image_id=%s source=%s platform=linux/amd64\n' \
    "$ROOT_ARTIFACT_ROLE" "$ROOT_ARTIFACT_REFERENCE" "$ROOT_ARTIFACT_IMAGE_ID" "$CPK_ROOT_SOURCE_REVISION"
}
