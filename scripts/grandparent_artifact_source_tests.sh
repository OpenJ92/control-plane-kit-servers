#!/bin/sh
# Owning source gate only: finite Docker/Git doubles; no daemon socket/provider.
set -eu
[ "$#" = 0 ] || exit 2
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
CONTROLLER=sha256:4eb536f196cb67260426f8902fca63959d414673c43bcd6e0008ff4712fd8c22
[ "$(docker image inspect "$CONTROLLER" --format '{{.Id}}')" = "$CONTROLLER" ] || exit 2
docker run --pull never --rm --network none --read-only --tmpfs /tmp:exec,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source \
  -e PYTHONPYCACHEPREFIX=/tmp/pycache --entrypoint sh "$CONTROLLER" -ec '
    sh -n test.sh
    sh -n scripts/cpk_server_image_smoke.sh
    sh -n scripts/grandparent_cpk_cutover.sh
    sh -n scripts/grandparent_saved_read.sh
    python -m py_compile scripts/grandparent_artifact_fixture.py
    python -m py_compile scripts/grandparent_cpk_cutover.py
    python -m py_compile scripts/grandparent_saved_read.py
  '
docker run --pull never --rm --network none --read-only --tmpfs /tmp:exec,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/source/src \
  --entrypoint python "$CONTROLLER" scripts/apply_coordinates.py --check
docker run --pull never --rm --network none --read-only --tmpfs /tmp:exec,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source/test_support \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/source/test_support -e CPK_PACKAGE_ROOT=/source \
  --entrypoint python "$CONTROLLER" -m unittest discover -s tests -v
docker run --pull never --rm --network none --read-only --tmpfs /tmp:exec,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source \
  -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python "$CONTROLLER" \
  /source/test_support/package_integrity.py --package-root /source \
  --source-root src --source-root products --test-root tests --test-root products --gate-file test.sh
docker run --pull never --rm --network none --read-only --tmpfs /tmp:exec,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/source/scripts \
  --entrypoint python "$CONTROLLER" -m unittest grandparent_build_tests grandparent_oci_tests grandparent_inventory_tests grandparent_qualification_driver_tests grandparent_witness_http_tests grandparent_cpk_cutover_tests -v
# Actual frozen installer imports/client/file-owner boundary, intercepted wire.
# Only public source and synthetic UID501 files exist; no socket or real input.
INSTALLER=sha256:0d5f36d8d2fa28ebcd01e895cd2db0e5b97df7bb5a15858bfd30442a21c09c80
[ "$(docker image inspect "$INSTALLER" --format '{{.Id}}')" = "$INSTALLER" ] || exit 2
docker run --pull never --rm --network none --read-only --tmpfs /tmp:exec,mode=1777,size=128m \
  --tmpfs /credentials:rw,mode=1777,size=1m \
  --user 0 --cap-drop ALL --cap-add DAC_READ_SEARCH --cap-add SETUID --cap-add SETGID --security-opt no-new-privileges \
  --cpus 1 --memory 512m --pids-limit 128 \
  --mount "type=bind,source=$ROOT,target=/source,readonly" --workdir /source/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python "$INSTALLER" \
  -m unittest grandparent_cutover_installer_tests.InstallerProcessContract -v
# Startup diagnosis: same physical file targets/UID/capability/proxy profile as
# the consumed read-only launch, synthetic files only, no network or socket.
STARTUP_CONTEXT=$(mktemp -d /private/tmp/cpk399-offline-startup.XXXXXX)
# Public/synthetic fixture context only; file modes are independently pinned.
chmod 777 "$STARTUP_CONTEXT"
finish_startup_context() {
  status=$?
  trap - 0
  rm -rf "$STARTUP_CONTEXT"
  [ ! -e "$STARTUP_CONTEXT" ] && [ ! -L "$STARTUP_CONTEXT" ] || status=1
  exit "$status"
}
trap finish_startup_context 0
docker run --pull never --rm --network none --read-only --user 501:20 --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=32m \
  --mount "type=bind,source=$ROOT,target=/source,readonly" \
  --mount "type=bind,source=$STARTUP_CONTEXT,target=/fixture" \
  -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python "$INSTALLER" \
  /source/scripts/grandparent_saved_read_startup_tests.py --make-fixture /fixture
docker run --pull never --rm --network none --read-only --user 501:20 --cap-drop ALL \
  --security-opt no-new-privileges --cpus 1 --memory 512m --pids-limit 64 \
  --tmpfs /tmp:rw,nosuid,nodev,size=32m --log-driver none \
  --env PYTHONDONTWRITEBYTECODE=1 --env HTTP_PROXY= --env HTTPS_PROXY= --env ALL_PROXY= \
  --env http_proxy= --env https_proxy= --env all_proxy= \
  --mount "type=bind,source=$ROOT/scripts/grandparent_saved_read.py,target=/grandparent_saved_read.py,readonly" \
  --mount "type=bind,source=$ROOT/scripts/grandparent_cpk_cutover.py,target=/grandparent_cpk_cutover.py,readonly" \
  --mount "type=bind,source=$STARTUP_CONTEXT/action.json,target=/proposal/verification.json,readonly" \
  --mount "type=bind,source=$STARTUP_CONTEXT/desired.json,target=/public/desired.json,readonly" \
  --mount "type=bind,source=$STARTUP_CONTEXT/human.bearer,target=/credentials/human.bearer,readonly" \
  --mount "type=bind,source=$ROOT,target=/source,readonly" \
  --mount "type=bind,source=$STARTUP_CONTEXT,target=/fixture,readonly" \
  --entrypoint python "$INSTALLER" /source/scripts/grandparent_saved_read_startup_tests.py --probe
