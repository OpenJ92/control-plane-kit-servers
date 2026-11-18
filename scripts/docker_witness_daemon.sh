# Local witness admission; source from the owning smoke, not a transport fallback.
docker_witness_daemon() {
  # This witness supports context-selected local sockets only. Do not guess
  # precedence when endpoint or TLS environment overrides are also supplied.
  if [ -n "${DOCKER_HOST:-}${DOCKER_TLS:-}${DOCKER_TLS_VERIFY:-}${DOCKER_CERT_PATH:-}" ]; then
    echo 'Docker image witness refuses endpoint or TLS overrides' >&2
    return 1
  fi
  DOCKER_CONTEXT="$(docker context show)" || return 1
  [ -n "$DOCKER_CONTEXT" ] || {
    echo 'Docker image witness requires a selected context' >&2
    return 1
  }
  export DOCKER_CONTEXT
  witness_endpoint="$(docker context inspect "$DOCKER_CONTEXT" --format '{{.Endpoints.docker.Host}}')" || return 1
  case "$witness_endpoint" in
    unix:///?*) ;;
    *) echo 'Docker image witness requires a local Unix endpoint' >&2; return 1 ;;
  esac
  image_witness_daemon="$(docker info --format '{{.ID}}')" || return 1
  [ -n "$image_witness_daemon" ] || {
    echo 'Docker image witness requires a nonempty daemon identity' >&2
    return 1
  }
}
