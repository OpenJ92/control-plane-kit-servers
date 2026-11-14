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
    python -m py_compile scripts/grandparent_artifact_fixture.py
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
  --entrypoint python "$CONTROLLER" -m unittest grandparent_build_tests grandparent_oci_tests grandparent_inventory_tests grandparent_qualification_driver_tests -v
