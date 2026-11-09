#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
MODE=run
if [ "${1:-}" = --admit ]; then MODE=admit; shift; fi
invalid() { echo 'gateway packaged inputs unavailable or invalid' >&2; exit 2; }
INPUT_SNAPSHOT=''
drop_input_snapshot() {
  [ -n "$INPUT_SNAPSHOT" ] || return 0
  rm -f "$INPUT_SNAPSHOT/pin.json" "$INPUT_SNAPSHOT/inputs.json" "$INPUT_SNAPSHOT/receipt.json" || return 1
  rmdir "$INPUT_SNAPSHOT" || return 1
  INPUT_SNAPSHOT=''
}
trap 'input_status=$?; trap - EXIT; drop_input_snapshot || input_status=1; exit "$input_status"' EXIT
sha256_file() {
  # Equivalent native metadata tools on the documented Linux/macOS hosts.
  if command -v sha256sum >/dev/null 2>&1; then
    digest_line=$(sha256sum "$1" 2>/dev/null) || return 1
  elif command -v shasum >/dev/null 2>&1; then
    digest_line=$(shasum -a 256 "$1" 2>/dev/null) || return 1
  else return 1
  fi
  printf '%s\n' "${digest_line%% *}"
}
one_object() { jq -s -e 'length==1 and (.[0]|type=="object" and length>0)' "$1" >/dev/null 2>&1; }
[ "$#" = 1 ] || invalid
INPUTS=$1
CPK_REF=localhost/control-plane-kit-servers/cpk-server@sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28
PG_REF=docker.io/library/postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777
CONTROLLER=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
GW_DAEMON=d23d00aa-b281-448d-bc95-c8e47efeeea2
SEED_SOURCE=1182fccdaed6e8d8410f7ec2b5de697ab8236c4b
GW_RUN=${CPK_GATEWAY_IMAGE_RUN:-cpk-gateway-image-smoke-cpk163-20261109-01}
CANONICAL_TMP=$(CDPATH= cd -- /tmp && pwd -P)
GW_RECORDS=$CANONICAL_TMP/$GW_RUN
TAG=${CPK_GATEWAY_IMAGE_TAG:-localhost/control-plane-kit-servers/cpk-local-gateway:cpk163-relay-20261109-01}
printf '%s\n' "$GW_RUN" | grep -Eq '^cpk-gateway-image-smoke-cpk163-[a-z0-9-]{4,32}$' || invalid
case "$TAG" in localhost/control-plane-kit-servers/cpk-local-gateway:cpk163-*) ;; *) invalid ;; esac
[ ! -e "$GW_RECORDS" ] && [ ! -L "$GW_RECORDS" ] || invalid
[ -f "$INPUTS" ] && [ ! -L "$INPUTS" ] || invalid
[ "$(wc -c < "$INPUTS")" -le 65536 ] || invalid
INPUT_SNAPSHOT=$(mktemp -d "$CANONICAL_TMP/cpk163-gateway-inputs.XXXXXXXX")
# Read the acceptance pin from the immutable Git tree, never an environment
# override or a mutable file. The committed null pin deliberately cannot pass.
ADMISSION_SOURCE=$(git rev-parse HEAD) || invalid
PIN_BLOB=$(git rev-parse "$ADMISSION_SOURCE:products/cpk_local_gateway/tests/packaged_secrets_acceptance.json") || invalid
git show "$ADMISSION_SOURCE:products/cpk_local_gateway/tests/packaged_secrets_acceptance.json" > "$INPUT_SNAPSHOT/pin.json" 2>/dev/null || invalid
one_object "$INPUT_SNAPSHOT/pin.json" || invalid
jq -e 'keys==["receipt_sha256","reference","run","schema","source","url"] and
 .schema=="cpk163.gateway-secrets-acceptance.v1" and .source=="1182fccdaed6e8d8410f7ec2b5de697ab8236c4b" and
 (.reference|type=="string" and test("^localhost/control-plane-kit-servers/secrets-server@sha256:[0-9a-f]{64}$")) and
 (.url|type=="string" and test("^https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-[0-9]+$")) and
 (.receipt_sha256|type=="string" and test("^[0-9a-f]{64}$")) and
 (.run|type=="string" and test("^cpk-secrets-image-smoke-cpk163-[a-z0-9-]{4,32}$"))' "$INPUT_SNAPSHOT/pin.json" >/dev/null 2>&1 || invalid
PIN_REF=$(jq -er .reference "$INPUT_SNAPSHOT/pin.json")
PIN_URL=$(jq -er .url "$INPUT_SNAPSHOT/pin.json")
PIN_HASH=$(jq -er .receipt_sha256 "$INPUT_SNAPSHOT/pin.json")
PIN_RUN=$(jq -er .run "$INPUT_SNAPSHOT/pin.json")
cp -P "$INPUTS" "$INPUT_SNAPSHOT/inputs.json" 2>/dev/null || invalid
INPUTS=$INPUT_SNAPSHOT/inputs.json
[ -f "$INPUTS" ] && [ ! -L "$INPUTS" ] || invalid
[ "$(wc -c < "$INPUTS")" -le 65536 ] || invalid
one_object "$INPUTS" || invalid
jq -e 'keys==["schema","secrets_acceptance","secrets_receipt","secrets_reference"] and
 .schema=="cpk163.gateway-image-inputs.v1" and
 (.secrets_reference|test("^localhost/control-plane-kit-servers/secrets-server@sha256:[0-9a-f]{64}$")) and
 (.secrets_acceptance|test("^https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-[0-9]+$")) and
 (.secrets_receipt|type=="string")' "$INPUTS" >/dev/null 2>&1 || invalid
SECRETS_REF=$(jq -er .secrets_reference "$INPUTS")
SECRETS_RECEIPT=$(jq -er .secrets_receipt "$INPUTS")
SECRETS_ACCEPTANCE=$(jq -er .secrets_acceptance "$INPUTS")
[ "$SECRETS_REF" = "$PIN_REF" ] && [ "$SECRETS_ACCEPTANCE" = "$PIN_URL" ] || invalid
printf '%s\n' "$SECRETS_RECEIPT" | grep -Eq "^$CANONICAL_TMP/cpk-secrets-image-smoke-cpk163-[a-z0-9-]{4,32}/result[.]json$" || invalid
[ "$SECRETS_RECEIPT" = "$CANONICAL_TMP/$PIN_RUN/result.json" ] || invalid
[ -f "$SECRETS_RECEIPT" ] && [ ! -L "$SECRETS_RECEIPT" ] || invalid
[ "$(wc -c < "$SECRETS_RECEIPT")" -le 65536 ] || invalid
cp -P "$SECRETS_RECEIPT" "$INPUT_SNAPSHOT/receipt.json" 2>/dev/null || invalid
SECRETS_RECEIPT=$INPUT_SNAPSHOT/receipt.json
[ -f "$SECRETS_RECEIPT" ] && [ ! -L "$SECRETS_RECEIPT" ] || invalid
[ "$(wc -c < "$SECRETS_RECEIPT")" -le 65536 ] || invalid
[ "$(sha256_file "$SECRETS_RECEIPT")" = "$PIN_HASH" ] || invalid
one_object "$SECRETS_RECEIPT" || invalid
jq -e --arg reference "$SECRETS_REF" --arg source "$SEED_SOURCE" --arg daemon "$GW_DAEMON" --arg controller "$CONTROLLER" --arg run "$PIN_RUN" '
 .run==$run and (.owner_nonce|test("^[0-9a-f]{64}$")) and
 .source==$source and .daemon_id==$daemon and .controller_id==$controller and
 .product_source_base=="85b193bbdc777376c5104029a5ee04e74627cf71" and .exit_code==0 and
 .candidate_reference==$reference and .cleanup=="verified" and .candidate_retention=="verified" and
 .installed_provenance_verified==true and .initial_custody_verified==true and
 .retained_restart_verified==true and .revocation_persistence_verified==true and
 .signed_pair_verified==true and .initial_signed_pair_verified==true and .restart_signed_pair_verified==true and
 .logs_redacted_verified==true' "$SECRETS_RECEIPT" >/dev/null 2>&1 || invalid
# Filling the Git pin requires North's real independent acceptance and review of
# its exact digest/URL/receipt bytes. A pin still does not grant execution release.
git diff --quiet "$SEED_SOURCE" -- products/secrets_server/tests/child_bootstrap_fixture.py || invalid
[ "$MODE" != admit ] || exit 0

GW_RESERVED=0 GW_OWNER='' GW_SOURCE='' GW_REFERENCE='' GW_IMAGE=''
GW_BUILD_ATTEMPTED=0 GW_BUILD=0 GW_PROVENANCE=0 GW_EXCHANGE=0 GW_LOGS=0 GW_PHASE=admission
GW_VOLUMES="$GW_RUN-pg-data $GW_RUN-secrets-bootstrap $GW_RUN-secrets-client $GW_RUN-secrets-data"
. ./scripts/gateway_packaged_owner.sh

snapshot() {
  snap_role=$1
  [ -s "$GW_RECORDS/$snap_role.cid" ] || return 1
  snap_id=$(cat "$GW_RECORDS/$snap_role.cid") || return 1
  gw_daemon || return 1
  docker inspect "$snap_id" --format '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"path":{{json .Path}},"args":{{json .Args}},"run":{{json (index .Config.Labels "cpk.test-run")}},"owner":{{json (index .Config.Labels "cpk.test-owner")}},"state":{"status":{{json .State.Status}},"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}}},"ports":{{json .HostConfig.PortBindings}},"networks":{{json .NetworkSettings.Networks}},"mounts":{{json .Mounts}}}' \
    > "$GW_RECORDS/$snap_role-$2.json" 2>/dev/null || return 1
  [ "$(wc -c < "$GW_RECORDS/$snap_role-$2.json")" -le 65536 ]
}

identity() {
  role=$1 expected_image=$2 uid=$3
  snapshot "$role" startup
  case "$role" in cpk) alias=cpk-source ;; secrets) alias=secrets-provider ;; gateway) alias=gateway-source ;; esac
  jq -e --arg image "$expected_image" --arg run "$GW_RUN" --arg owner "$GW_OWNER" --arg role "$role" --arg alias "$alias" '
    .image==$image and .name==("/"+$run+"-"+$role) and .run==$run and .owner==$owner and
    .state.running==true and ((.ports//{})|length==0) and (.networks|keys==[$run]) and
    (.networks[$run].Aliases|index($alias)!=null)' \
    "$GW_RECORDS/$role-startup.json" >/dev/null
  case "$role" in
    cpk|gateway)
      if [ "$role" = cpk ]; then module=control_plane_kit_servers_cpk_server.server; else module=control_plane_kit_servers_cpk_local_gateway.server; fi
      jq -e --arg module "$module" '.path=="python" and .args==["-m",$module]' "$GW_RECORDS/$role-startup.json" >/dev/null ;;
    secrets)
      jq -e '(.path=="cpk-secrets-entrypoint" or .path=="/usr/local/bin/cpk-secrets-entrypoint") and .args==["uvicorn","control_plane_kit_servers_secrets_server.server:create_app","--factory","--host","0.0.0.0","--port","8081"]' \
        "$GW_RECORDS/$role-startup.json" >/dev/null ;;
  esac
  case "$role" in
    cpk) jq -e '(.mounts|length)==2 and all(.mounts[];.Type=="bind" and .RW==false) and
      ([.mounts[].Destination]|sort)==["/etc/cpk/cpk-server/control.json","/etc/cpk/cpk-server/http-samples.json"]' "$GW_RECORDS/$role-startup.json" >/dev/null ;;
    gateway) jq -e '(.mounts|length)==4 and all(.mounts[];.Type=="bind" and .RW==false) and
      ([.mounts[].Destination]|sort)==["/etc/cpk/gateway/control.json","/etc/cpk/gateway/health-targets.json","/etc/cpk/gateway/health-transit.json","/etc/cpk/gateway/http-sample-transit.json"]' "$GW_RECORDS/$role-startup.json" >/dev/null ;;
    secrets) jq -e --arg run "$GW_RUN" '(.mounts|length)==4 and
      any(.mounts[];.Destination=="/etc/cpk/secrets-server/control.json" and .Type=="bind" and .RW==false) and
      any(.mounts[];.Destination=="/etc/cpk/secrets-server/http-samples.json" and .Type=="bind" and .RW==false) and
      any(.mounts[];.Destination=="/run/secrets/cpk-secrets" and .Name==($run+"-secrets-bootstrap") and .RW==false) and
      any(.mounts[];.Destination=="/var/lib/cpk-secrets" and .Name==($run+"-secrets-data") and .RW==true)' "$GW_RECORDS/$role-startup.json" >/dev/null ;;
  esac
  process=$(cat "$GW_RECORDS/$role.cid")
  docker exec "$process" python -c '
import json,sys
with open("/proc/1/status","rb") as stream: raw=stream.read(16385)
rows=[line.split()[1:] for line in raw.splitlines() if line.startswith(b"Uid:")]
if len(raw)>16384 or len(rows)!=1 or len(rows[0])!=4 or int(rows[0][1])!=int(sys.argv[1]): raise SystemExit(1)
print(json.dumps({"pid":1,"effective_uid":int(sys.argv[1])}))
' "$uid" > "$GW_RECORDS/$role-process.json"
}

finish() {
  status=$?
  trap - EXIT INT TERM
  cleanup=not-started retention=not-observed
  if [ "$GW_RESERVED" = 1 ]; then
    for role in postgres cpk secrets gateway; do
      if [ -f "$GW_RECORDS/$role.attempt" ]; then
        if snapshot "$role" before-cleanup; then
          if [ "$status" = 0 ]; then
            jq -e '.state.running==true and .state.oom_killed==false' "$GW_RECORDS/$role-before-cleanup.json" >/dev/null || status=1
          fi
        else status=1
        fi
      fi
    done
    cleanup=verified
    gw_cleanup || { status=1; cleanup=unverified; }
    for role in postgres cpk secrets gateway signer; do
      rm -f "$GW_RECORDS/private/$role.log" "$GW_RECORDS/private/$role.status" || { status=1; cleanup=unverified; }
    done
    if [ -d "$GW_RECORDS/private" ]; then rmdir "$GW_RECORDS/private" || { status=1; cleanup=unverified; }; fi
    retention=verified
    : > "$GW_RECORDS/retained-images.jsonl"
    if gw_daemon; then
      for reference in "$CPK_REF" "$SECRETS_REF" "$PG_REF" "$CONTROLLER" "$GW_REFERENCE"; do
        [ -n "$reference" ] || { status=1; retention=unverified; continue; }
        retained=$(docker image inspect "$reference" --format '{"id":{{json .Id}},"os":{{json .Os}},"architecture":{{json .Architecture}}}') || { status=1; retention=unverified; continue; }
        case "$reference" in
          "$CPK_REF") expected=$CPK_ATTRS ;; "$SECRETS_REF") expected=$SECRETS_ATTRS ;;
          "$PG_REF") expected=$PG_ATTRS ;; "$CONTROLLER") expected=$CONTROLLER_ATTRS ;;
          *) expected=$(cat "$GW_RECORDS/image.json") ;;
        esac
        if printf '%s' "$retained" | jq -e --argjson expected "$expected" \
            '.==($expected|{id,os,architecture})' >/dev/null; then :; else status=1; retention=unverified; fi
        printf '%s' "$retained" | jq -c --arg reference "$reference" '.+{reference:$reference}' >> "$GW_RECORDS/retained-images.jsonl" || { status=1; retention=unverified; }
      done
    else status=1; retention=unverified
    fi
    drop_input_snapshot || { status=1; cleanup=unverified; }
    jq -n --arg source "$GW_SOURCE" --arg run "$GW_RUN" --arg phase "$GW_PHASE" --arg owner "$GW_OWNER" \
      --arg gateway "$GW_REFERENCE" --arg cpk "$CPK_REF" --arg secrets "$SECRETS_REF" --arg postgres "$PG_REF" \
      --arg acceptance "$SECRETS_ACCEPTANCE" --arg cleanup "$cleanup" --arg retention "$retention" \
      --arg receipt_hash "$PIN_HASH" --arg receipt_run "$PIN_RUN" --arg seed "$SEED_SOURCE" \
      --arg daemon "$GW_DAEMON" --arg controller "$CONTROLLER" \
      --argjson status "$status" --argjson attempted "$GW_BUILD_ATTEMPTED" --argjson built "$GW_BUILD" --argjson provenance "$GW_PROVENANCE" \
      --argjson exchange "$GW_EXCHANGE" --argjson logs "$GW_LOGS" \
      '{source:$source,run:$run,phase:$phase,owner_nonce:$owner,exit_code:$status,
        gateway_reference:$gateway,cpk_reference:$cpk,secrets_reference:$secrets,postgres_reference:$postgres,
        daemon_id:$daemon,controller_id:$controller,secrets_receipt_sha256:$receipt_hash,
        secrets_receipt_run:$receipt_run,exclusive_seed_source:$seed,
        secrets_acceptance:$acceptance,gateway_build_attempted:($attempted==1),gateway_candidate_verified:($built==1),installed_provenance_verified:($provenance==1),
        packaged_exchange_verified:($exchange==1),logs_redacted_verified:($logs==1),cleanup:$cleanup,
        retained_inputs_and_candidate:$retention,approved_child_run:false}' > "$GW_RECORDS/result.json" || status=1
  else drop_input_snapshot || status=1
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

. ./scripts/docker_witness_daemon.sh
docker_witness_daemon
gw_daemon
GW_SOURCE=$(git rev-parse HEAD)
[ "$GW_SOURCE" = "$ADMISSION_SOURCE" ] || exit 1
worktree=$(git status --porcelain) || exit 1
[ -z "$worktree" ] || exit 1
git diff --quiet 85b193bbdc777376c5104029a5ee04e74627cf71 HEAD -- products/cpk_local_gateway/src products/cpk_local_gateway/Dockerfile coordinates/server-products.json
for role in cpk secrets postgres controller; do
  case "$role" in cpk) reference=$CPK_REF ;; secrets) reference=$SECRETS_REF ;; postgres) reference=$PG_REF ;; controller) reference=$CONTROLLER ;; esac
  # PG/controller eligibility never reads optional Labels or Config/Env.
  image_format='{"id":{{json .Id}},"digests":{{json .RepoDigests}},"os":{{json .Os}},"architecture":{{json .Architecture}}'
  case "$role" in
    cpk) image_format="$image_format"',"source":{{with (index .Config "Labels")}}{{json (index . "org.opencontainers.image.revision")}}{{else}}null{{end}}' ;;
    secrets) image_format="$image_format"',"source":{{with (index .Config "Labels")}}{{json (index . "org.opencontainers.image.revision")}}{{else}}null{{end}},"run":{{with (index .Config "Labels")}}{{json (index . "cpk.test-run")}}{{else}}null{{end}},"owner":{{with (index .Config "Labels")}}{{json (index . "cpk.test-owner")}}{{else}}null{{end}}' ;;
  esac
  attrs=$(docker image inspect "$reference" --format "$image_format}" 2>/dev/null) || {
    printf 'gateway borrowed image inspection failed: %s\n' "$role" >&2
    exit 1
  }
  image_id=$(printf '%s' "$attrs" | jq -er .id)
  if [ "$role" = controller ]; then
    [ "$image_id" = "$CONTROLLER" ] || exit 1
  else
    # Docker familiarizes this one fixed Docker Hub repository as postgres@….
    # Both spellings must carry the exact approved digest; no tag/hash fallback.
    digest_alias=$reference
    if [ "$role" = postgres ]; then digest_alias="postgres@${PG_REF#*@}"; fi
    printf '%s' "$attrs" | jq -e --arg reference "$reference" --arg alias "$digest_alias" \
      '.os=="linux" and ((.digests|index($reference)!=null) or (.digests|index($alias)!=null))' >/dev/null
  fi
  case "$role" in
    cpk) CPK_ID=$image_id; CPK_ATTRS=$attrs; printf '%s' "$attrs" | jq -e '.architecture=="amd64" and .source=="c04f060fd063b407d858c8a55fe85a247be086cf"' >/dev/null ;;
    secrets) SECRETS_ID=$image_id; SECRETS_ATTRS=$attrs
      receipt_owner=$(jq -er .owner_nonce "$SECRETS_RECEIPT")
      printf '%s' "$attrs" | jq -e --arg source "$SEED_SOURCE" --arg run "$PIN_RUN" --arg owner "$receipt_owner" \
        '.architecture=="amd64" and .source==$source and .run==$run and .owner==$owner' >/dev/null ;;
    postgres) PG_ID=$image_id; PG_ATTRS=$attrs ;;
    controller) CONTROLLER_ATTRS=$attrs ;;
  esac
done
existing=$(docker image ls -q --filter "reference=$TAG")
[ -z "$existing" ] || exit 1
for kind in container volume network; do
  case "$kind" in container) set -- ps -aq ;; volume) set -- volume ls -q ;; network) set -- network ls -q ;; esac
  existing=$(docker "$@" --filter "label=cpk.test-run=$GW_RUN")
  [ -z "$existing" ] || exit 1
done
for volume in $GW_VOLUMES; do existing=$(docker volume ls -q --filter "name=$volume"); [ -z "$existing" ] || exit 1; done
existing=$(docker network ls -q --filter "name=^$GW_RUN$")
[ -z "$existing" ] || exit 1
for role in $GW_ROLES; do existing=$(docker ps -aq --filter "name=^/$GW_RUN-$role$"); [ -z "$existing" ] || exit 1; done
mkdir -m 700 "$GW_RECORDS"
GW_RESERVED=1
GW_OWNER=$(od -An -N32 -tx1 /dev/urandom)
GW_OWNER=$(printf '%s' "$GW_OWNER" | tr -d '[:space:]')
[ "${#GW_OWNER}" = 64 ] || exit 1
case "$GW_OWNER" in *[!0-9a-f]*) exit 1 ;; esac
cp "$INPUTS" "$GW_RECORDS/inputs.json"
cp "$SECRETS_RECEIPT" "$GW_RECORDS/secrets-result.json"
cp "$INPUT_SNAPSHOT/pin.json" "$GW_RECORDS/secrets-acceptance.json"
[ "$(sha256_file "$GW_RECORDS/secrets-result.json")" = "$PIN_HASH" ] || { rm -f "$GW_RECORDS/secrets-result.json"; exit 1; }
[ "$(git hash-object "$GW_RECORDS/secrets-acceptance.json")" = "$PIN_BLOB" ] || exit 1
jq -n --argjson cpk "$CPK_ATTRS" --argjson secrets "$SECRETS_ATTRS" --argjson postgres "$PG_ATTRS" --argjson controller "$CONTROLLER_ATTRS" \
  '{cpk:$cpk,secrets:$secrets,postgres:$postgres,controller:$controller}' > "$GW_RECORDS/borrowed-images.json"
GW_PHASE=gateway-build
git archive --format=tar "$GW_SOURCE" > "$GW_RECORDS/source.tar"
gw_daemon
GW_BUILD_ATTEMPTED=1
docker buildx build --builder "$DOCKER_CONTEXT" --platform linux/amd64 --load \
  -f products/cpk_local_gateway/Dockerfile --label "org.opencontainers.image.revision=$GW_SOURCE" \
  --label "cpk.test-run=$GW_RUN" --label "cpk.test-owner=$GW_OWNER" --iidfile "$GW_RECORDS/image.id" \
  --metadata-file "$GW_RECORDS/build-metadata.json" -t "$TAG" - < "$GW_RECORDS/source.tar" > "$GW_RECORDS/build.log" 2>&1
GW_IMAGE=$(cat "$GW_RECORDS/image.id")
gw_daemon
worktree=$(git status --porcelain) || exit 1
[ -z "$worktree" ] || exit 1
[ "$(git rev-parse HEAD)" = "$GW_SOURCE" ] || exit 1
docker image inspect "$GW_IMAGE" --format '{"id":{{json .Id}},"digests":{{json .RepoDigests}},"os":{{json .Os}},"architecture":{{json .Architecture}},"user":{{json .Config.User}},"cmd":{{json .Config.Cmd}}}' > "$GW_RECORDS/image.json"
jq -e '.os=="linux" and .architecture=="amd64" and .user=="gateway" and .cmd==["python","-m","control_plane_kit_servers_cpk_local_gateway.server"]' "$GW_RECORDS/image.json" >/dev/null
GW_REFERENCE=$(jq -er --slurpfile metadata "$GW_RECORDS/build-metadata.json" '[.digests[]|select(.==("localhost/control-plane-kit-servers/cpk-local-gateway@"+$metadata[0]["containerimage.digest"]))]|unique|if length==1 then .[0] else error("missing gateway digest") end' "$GW_RECORDS/image.json")
[ "$(docker image inspect "$GW_REFERENCE" --format '{{.Id}}')" = "$GW_IMAGE" ] || exit 1
GW_BUILD=1
GW_PHASE=gateway-provenance
gw_run provenance --rm --network none --read-only \
  --mount "type=bind,source=$ROOT/products/cpk_local_gateway/tests/packaged_image_check.py,target=/witness.py,readonly" \
  --mount "type=bind,source=$ROOT/coordinates/server-products.json,target=/coordinates.json,readonly" \
  --entrypoint python "$GW_IMAGE" /witness.py provenance /coordinates.json > "$GW_RECORDS/installed-origins.json"
GW_PROVENANCE=1
GW_PHASE=owned-bootstrap
gw_daemon
(umask 077; : > "$GW_RECORDS/network.attempt")
docker network create --internal --label "cpk.test-run=$GW_RUN" --label "cpk.test-owner=$GW_OWNER" "$GW_RUN" >/dev/null
gw_network_identity "$GW_RUN"
for volume in $GW_VOLUMES; do gw_volume_create "$volume"; done
for volume in $GW_VOLUMES; do gw_volume_identity "$volume"; done
gw_run bootstrap --rm --network none --user 0:0 \
  --mount "type=volume,source=$GW_RUN-pg-data,target=/postgres-data" \
  --mount "type=volume,source=$GW_RUN-secrets-bootstrap,target=/provider-bootstrap" \
  --mount "type=volume,source=$GW_RUN-secrets-client,target=/client-bootstrap" \
  --mount "type=volume,source=$GW_RUN-secrets-data,target=/provider-data" \
  --mount "type=bind,source=$ROOT/products/secrets_server/tests/child_bootstrap_fixture.py,target=/seed.py,readonly" \
  --entrypoint python "$SECRETS_ID" -c 'import os,runpy
fd=os.open("/postgres-data",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
    if os.listdir(fd): raise SystemExit("gateway PostgreSQL fixture is not empty")
finally: os.close(fd)
runpy.run_path("/seed.py",run_name="__main__")'
gw_run postgres -d --network "$GW_RUN" --network-alias cpk-postgres \
  --mount "type=volume,source=$GW_RUN-pg-data,target=/var/lib/postgresql/data" \
  -e POSTGRES_DB=cpk -e POSTGRES_USER=cpk -e POSTGRES_PASSWORD=cpk "$PG_ID" >/dev/null
ready=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if docker exec -e PGPASSWORD=cpk "$(cat "$GW_RECORDS/postgres.cid")" psql -h 127.0.0.1 -U cpk -d cpk -c 'SELECT 1' >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || exit 1
GW_PHASE=public-fixture
mkdir -m 700 "$GW_RECORDS/fixture"
gw_run signer -d --network "$GW_RUN" --read-only --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --workdir /source -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/source:/source/products/cpk_local_gateway/src:/source/products/cpk_local_gateway/tests:/source/products/cpk_server/src:/source/products/secrets_server/src \
  --mount "type=bind,source=$ROOT,target=/source,readonly" \
  --mount "type=bind,source=$GW_RECORDS/fixture,target=/fixture" \
  "$CONTROLLER" python products/cpk_local_gateway/tests/packaged_sample_fixture.py /fixture/public >/dev/null
prepared=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if [ -f "$GW_RECORDS/fixture/public/prepared" ]; then prepared=1; break; fi
  [ "$(docker inspect "$(cat "$GW_RECORDS/signer.cid")" --format '{{.State.Running}}')" = true ] || break
  sleep 1
done
[ "$prepared" = 1 ] || exit 1
PUBLIC=$GW_RECORDS/fixture/public
GW_PHASE=retained-receivers-and-gateway
DB=postgresql://cpk:cpk@cpk-postgres:5432/cpk
gw_run cpk -d --network "$GW_RUN" --network-alias cpk-source --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$PUBLIC/cpk/control.json,target=/etc/cpk/cpk-server/control.json,readonly" \
  --mount "type=bind,source=$PUBLIC/cpk/http-samples.json,target=/etc/cpk/cpk-server/http-samples.json,readonly" \
  -e CPK_HTTP_VERIFICATION_SAMPLES_CONFIGURATION_FILE=/etc/cpk/cpk-server/http-samples.json \
  -e CPK_SERVER_MODE=execution-capable -e CPK_RUNTIME_INTERPRETERS=none -e CPK_PORT=8080 \
  -e CPK_CONTROL_AUTH_VERIFIER=static-development -e CPK_CONTROL_AUTH_STATIC_CREDENTIAL=valid-token \
  -e 'CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON={"root-workspace":["instance:workspace:read"]}' \
  -e "CPK_WORKPLACE_DATABASE_URL=$DB" -e "CPK_ACTIVITY_HISTORY_DATABASE_URL=$DB" \
  -e "CPK_OBSERVER_STATE_DATABASE_URL=$DB" -e "CPK_GRAPH_TOPOLOGY_DATABASE_URL=$DB" "$CPK_ID" >/dev/null
gw_run secrets -d --network "$GW_RUN" --network-alias secrets-provider --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=volume,source=$GW_RUN-secrets-bootstrap,target=/run/secrets/cpk-secrets,readonly" \
  --mount "type=volume,source=$GW_RUN-secrets-data,target=/var/lib/cpk-secrets" \
  --mount "type=bind,source=$PUBLIC/secrets/control.json,target=/etc/cpk/secrets-server/control.json,readonly" \
  --mount "type=bind,source=$PUBLIC/secrets/http-samples.json,target=/etc/cpk/secrets-server/http-samples.json,readonly" \
  -e CPK_HTTP_VERIFICATION_SAMPLES_CONFIGURATION_FILE=/etc/cpk/secrets-server/http-samples.json "$SECRETS_ID" >/dev/null
gw_run gateway -d --network "$GW_RUN" --network-alias gateway-source --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$PUBLIC/gateway/control.json,target=/etc/cpk/gateway/control.json,readonly" \
  --mount "type=bind,source=$PUBLIC/gateway/health-transit.json,target=/etc/cpk/gateway/health-transit.json,readonly" \
  --mount "type=bind,source=$PUBLIC/gateway/health-targets.json,target=/etc/cpk/gateway/health-targets.json,readonly" \
  --mount "type=bind,source=$PUBLIC/gateway/http-sample-transit.json,target=/etc/cpk/gateway/http-sample-transit.json,readonly" \
  -e CPK_GATEWAY_HTTP_SAMPLE_TRANSIT_CONFIGURATION_FILE=/etc/cpk/gateway/http-sample-transit.json "$GW_IMAGE" >/dev/null
GW_PHASE=owned-readiness
gw_run readiness --rm --network "$GW_RUN" --read-only \
  --mount "type=bind,source=$ROOT/products/cpk_local_gateway/tests/packaged_image_check.py,target=/check.py,readonly" \
  "$CONTROLLER" python /check.py readiness > "$GW_RECORDS/readiness.json"
identity cpk "$CPK_ID" 10001
identity secrets "$SECRETS_ID" 10006
identity gateway "$GW_IMAGE" 10005
GW_PHASE=packaged-exchanges
: > "$PUBLIC/ready"
gw_wait_signer
jq -e '.approved_run==false and (.samples|length)==4 and all(.samples[];.passed==true) and (.health_relays|length)==2 and all(.health_relays[];.passed==true)' "$PUBLIC/samples.json" >/dev/null
cp "$PUBLIC/samples.json" "$GW_RECORDS/samples.json"
GW_EXCHANGE=1
GW_PHASE=redacted-logs
mkdir -m 700 "$GW_RECORDS/private"
for role in postgres cpk secrets gateway signer; do
  (umask 077; : > "$GW_RECORDS/private/$role.log"; : > "$GW_RECORDS/private/$role.status")
  (set +e; docker logs "$(cat "$GW_RECORDS/$role.cid")" 2>&1; log_status=$?; printf '%s\n' "$log_status" > "$GW_RECORDS/private/$role.status") \
    | head -c 1048577 > "$GW_RECORDS/private/$role.log"
done
gw_run logs --rm --network none --read-only --user 0:0 \
  --mount "type=bind,source=$ROOT/products/cpk_local_gateway/tests/packaged_image_check.py,target=/check.py,readonly" \
  --mount "type=bind,source=$GW_RECORDS/private,target=/logs,readonly" \
  --mount "type=volume,source=$GW_RUN-secrets-bootstrap,target=/provider,readonly" \
  --mount "type=volume,source=$GW_RUN-secrets-client,target=/client,readonly" \
  "$CONTROLLER" python /check.py logs /logs > "$GW_RECORDS/log-redaction.json"
GW_LOGS=1
gw_daemon
worktree=$(git status --porcelain) || exit 1
[ -z "$worktree" ] || exit 1
[ "$(git rev-parse HEAD)" = "$GW_SOURCE" ] || exit 1
GW_PHASE=complete
