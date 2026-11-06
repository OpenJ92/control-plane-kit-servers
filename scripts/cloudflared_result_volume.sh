#!/bin/sh
# Product-owned scratch transport for the two managed witness shell owners.
# Calls are single attempts. The fresh run namespace has no competing writer.
set -eu
managed_result_acquire() (
  set -eu
  run=$1 records=$2
  volume="$run-results"
  record="$records/result-volume.json"
  [ ! -e "$record" ] && [ ! -L "$record" ]
  observed="$(docker volume ls -q --filter "name=$volume")"
  [ -z "$observed" ]
  jq -n --arg run "$run" --arg volume "$volume" \
    '{schema:"cpk.managed-result-volume.v1",run:$run,volume:$volume,acquired:false}' > "$record"
  # A failed create or receipt write preserves the proposed name as uncertain.
  created="$(docker volume create --driver local --label "org.openj92.cpk.test-run=$run" \
      --label org.openj92.project=control-plane-kit-servers "$volume")"
  [ "$created" = "$volume" ]
  observed="$(docker volume inspect "$volume")"
  printf '%s\n' "$observed" | jq -e --arg run "$run" --arg volume "$volume" '
    if length == 1 and .[0].Name == $volume and .[0].Driver == "local" and
       .[0].Scope == "local" and (.[0].Options == null or .[0].Options == {}) and
       .[0].Labels["org.openj92.cpk.test-run"] == $run and
       .[0].Labels["org.openj92.project"] == "control-plane-kit-servers" and
       (.[0].CreatedAt | type == "string" and length > 0 and length <= 128)
    then {schema:"cpk.managed-result-volume.v1",run:$run,volume:$volume,
          acquired:true,created_at:.[0].CreatedAt} else error("result volume association") end
  ' > "$record.tmp"
  mv "$record.tmp" "$record"
)

managed_result_remove() (
  set -eu
  run=$1 records=$2
  volume="$run-results"
  record="$records/result-volume.json"
  empty="$records/result-volume.empty.json"
  for file in "$record" "$empty"; do
    [ -f "$file" ] && [ ! -L "$file" ] && [ "$(wc -c < "$file")" -le 4096 ]
  done
  jq -e --arg run "$run" --arg volume "$volume" '
    .schema == "cpk.managed-result-volume.v1" and .run == $run and .volume == $volume and
    .acquired == true and (.created_at | type == "string" and length > 0 and length <= 128)
  ' "$record" >/dev/null
  jq -e --arg run "$run" --arg volume "$volume" '
    . == {schema:"cpk.managed-result-empty.v1",run:$run,volume:$volume,empty:true}
  ' "$empty" >/dev/null
  observed="$(docker volume inspect "$volume")"
  printf '%s\n' "$observed" | jq -e --arg run "$run" --arg volume "$volume" \
    --arg created "$(jq -r .created_at "$record")" '
    length == 1 and .[0].Name == $volume and .[0].Driver == "local" and
    .[0].Scope == "local" and (.[0].Options == null or .[0].Options == {}) and
    .[0].CreatedAt == $created and .[0].Labels["org.openj92.cpk.test-run"] == $run and
    .[0].Labels["org.openj92.project"] == "control-plane-kit-servers"
  ' >/dev/null
  references="$(docker container ls -aq --filter "volume=$volume")"
  [ -z "$references" ]
  docker volume rm "$volume" >/dev/null
  observed="$(docker volume ls -q --filter "name=$volume")"
  [ -z "$observed" ]
)

case "${1:-}" in
  acquire) shift; [ "$#" = 2 ]; managed_result_acquire "$@" ;;
  remove) shift; [ "$#" = 2 ]; managed_result_remove "$@" ;;
  *) exit 2 ;;
esac
