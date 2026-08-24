#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CPK_CANDIDATE_ROOT=${CPK_CANDIDATE_ROOT:?CPK_CANDIDATE_ROOT is required}
ASSEMBLY=${CPK_CANDIDATE_ASSEMBLY:-$ROOT/candidate-assembly.json}
INSPECTION=${CPK_CANDIDATE_INSPECTION:-$ROOT/candidate-inspection.json}
REPORT=${CPK_CANDIDATE_REPORT:-$ROOT/candidate-topology-report.json}
LEDGER=${CPK_CANDIDATE_LEDGER:-$(dirname "$REPORT")/candidate-run-ledger.json}
PROJECT_LABEL=org.openj92.project=control-plane-kit-servers
SCENARIO_LABEL=org.openj92.cpk.scenario=candidate-topology-1714
EVIDENCE_ID=${CPK_CANDIDATE_EVIDENCE_ID:?CPK_CANDIDATE_EVIDENCE_ID is required}
EVIDENCE_LABEL=org.openj92.cpk.evidence=$EVIDENCE_ID
CPK_SERVER_BASE_IMAGE=${CPK_SERVER_BASE_IMAGE:?CPK_SERVER_BASE_IMAGE is required}
TIMEOUT_SECONDS=${CPK_CANDIDATE_TIMEOUT_SECONDS:-900}
RFC8785_WHEEL_URL=https://files.pythonhosted.org/packages/4d/78/119878110660b2ad709888c8a1614fce7e2fab39080ab960656dc8605bf6/rfc8785-0.1.4-py3-none-any.whl
RFC8785_WHEEL_SHA256=520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48
RFC8785_WHEEL_SIZE=9240
DIST_ROOT=$ROOT/dist
INTERRUPT_AFTER=${CPK_CANDIDATE_INTERRUPT_AFTER:-}
SUPERVISOR_CLASSIFICATION=failed-contained

SERVER_COMMIT=$(git -C "$ROOT" rev-parse HEAD)
SERVER_TREE=$(git -C "$ROOT" rev-parse HEAD^{tree})
git -C "$ROOT" diff --quiet
git -C "$ROOT" diff --cached --quiet
CPK_COMMIT=$(git -C "$CPK_CANDIDATE_ROOT" rev-parse HEAD)
CPK_TREE=$(git -C "$CPK_CANDIDATE_ROOT" rev-parse HEAD^{tree})
git -C "$CPK_CANDIDATE_ROOT" diff --quiet
git -C "$CPK_CANDIDATE_ROOT" diff --cached --quiet

sha256_file() {
    shasum -a 256 "$1" | awk '{print $1}'
}

supervisor_cleanup() {
    python -m scripts.cpk_server_candidate_lifecycle cleanup \
        --ledger "$LEDGER" \
        --classification "$SUPERVISOR_CLASSIFICATION"
}

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    supervisor_cleanup || exit 97
    exit "$status"
}

python -m scripts.cpk_server_candidate_lifecycle declare \
    --ledger "$LEDGER" \
    --root "$ROOT" \
    --evidence-id "$EVIDENCE_ID" \
    --project-label "$PROJECT_LABEL" \
    --scenario-label "$SCENARIO_LABEL"
trap cleanup EXIT HUP INT TERM

mkdir -p "$DIST_ROOT"
cp "$CPK_CANDIDATE_ROOT/dist/control_plane_kit_core.whl" "$DIST_ROOT/control_plane_kit_core.whl"
cp "$CPK_CANDIDATE_ROOT/dist/control_plane_kit_operations.whl" "$DIST_ROOT/control_plane_kit_operations.whl"
curl -fsSL "$RFC8785_WHEEL_URL" -o "$DIST_ROOT/rfc8785-0.1.4-py3-none-any.whl"
test "$(wc -c < "$DIST_ROOT/rfc8785-0.1.4-py3-none-any.whl" | tr -d ' ')" = "$RFC8785_WHEEL_SIZE"
test "$(sha256_file "$DIST_ROOT/rfc8785-0.1.4-py3-none-any.whl")" = "$RFC8785_WHEEL_SHA256"

PRODUCTION_DOCKERFILE_SHA256=$(sha256_file "$CPK_CANDIDATE_ROOT/products/cpk_server/Dockerfile")
OVERLAY_SHA256=$(sha256_file "$ROOT/acceptance/candidate_topology/Dockerfile")
CORE_WHEEL_SHA256=$(sha256_file "$DIST_ROOT/control_plane_kit_core.whl")
OPERATIONS_WHEEL_SHA256=$(sha256_file "$DIST_ROOT/control_plane_kit_operations.whl")
OBSERVED_RFC8785_WHEEL_SHA256=$(sha256_file "$DIST_ROOT/rfc8785-0.1.4-py3-none-any.whl")
BASE_IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$CPK_SERVER_BASE_IMAGE")

python - "$ASSEMBLY" "$INSPECTION" \
    "$SERVER_COMMIT" "$SERVER_TREE" "$CPK_COMMIT" "$CPK_TREE" \
    "$PRODUCTION_DOCKERFILE_SHA256" "$OVERLAY_SHA256" \
    "$CORE_WHEEL_SHA256" "$OPERATIONS_WHEEL_SHA256" \
    "$OBSERVED_RFC8785_WHEEL_SHA256" "$BASE_IMAGE_ID" <<'PY'
import json
from pathlib import Path
import sys

(
    assembly_path,
    inspection_path,
    server_commit,
    server_tree,
    candidate_commit,
    candidate_tree,
    production_dockerfile,
    overlay,
    core_wheel,
    operations_wheel,
    rfc8785_wheel,
    base_image,
) = sys.argv[1:]
assembly = json.loads(Path(assembly_path).read_text(encoding="utf-8"))
inspection = json.loads(Path(inspection_path).read_text(encoding="utf-8"))
expected_server = {
    "repository": "OpenJ92/control-plane-kit-servers",
    "commit": server_commit,
    "tree": server_tree,
}
expected_files = {
    "products/cpk_server/Dockerfile": production_dockerfile,
    "acceptance/candidate_topology/Dockerfile": overlay,
    "dist/control_plane_kit_core.whl": core_wheel,
    "dist/control_plane_kit_operations.whl": operations_wheel,
    "dist/rfc8785-0.1.4-py3-none-any.whl": rfc8785_wheel,
}
if assembly.get("server_source") != expected_server:
    raise SystemExit("candidate source measurement is incongruent")
if assembly.get("runner") != expected_server:
    raise SystemExit("candidate runner measurement is incongruent")
if inspection.get("server_source") != {
    "commit": server_commit,
    "tree": server_tree,
    "clean": True,
}:
    raise SystemExit("candidate server inspection is incongruent")
if inspection.get("candidate") != {
    "commit": candidate_commit,
    "tree": candidate_tree,
    "clean": True,
}:
    raise SystemExit("candidate package inspection is incongruent")
if inspection.get("files") != expected_files:
    raise SystemExit("candidate artifact inspection is incongruent")
if inspection.get("images") != {"cpk_server_base": base_image}:
    raise SystemExit("candidate base image inspection is incongruent")
PY

# The admitted inspection owns CPK_SERVER_BASE_IMAGE. The runner owns
# sync_runtime_networks=False, the labelled probe, and terminal report truth.
cd "$ROOT"
if test -n "$INTERRUPT_AFTER"; then
    test "$INTERRUPT_AFTER" = candidate-image-built
    set -- --interrupt-after "$INTERRUPT_AFTER"
else
    set --
fi
set +e
timeout "$TIMEOUT_SECONDS" python -m scripts.cpk_server_candidate_topology \
    --assembly "$ASSEMBLY" \
    --inspection "$INSPECTION" \
    --report "$REPORT" \
    --project-label "$PROJECT_LABEL" \
    --scenario-label "$SCENARIO_LABEL" \
    --evidence-id "$EVIDENCE_ID" \
    --ownership-ledger "$LEDGER" \
    "$@"
runner_exit=$?
set -e

if test -n "$INTERRUPT_AFTER"; then
    test "$runner_exit" -eq 86
    SUPERVISOR_CLASSIFICATION=interrupted-contained
    supervisor_cleanup
    trap - EXIT HUP INT TERM
    exit 86
fi
if test "$runner_exit" -ne 0; then
    supervisor_cleanup
    trap - EXIT HUP INT TERM
    exit "$runner_exit"
fi

test -s "$REPORT"
python - "$REPORT" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "first_failed_stage",
    "report_sha256",
    "cleanup",
    "observations",
}
if not required.issubset(report):
    raise SystemExit("candidate report publication is incomplete")
observations = report["observations"]
for name in ("pre_inventory", "post_inventory", "postgres_relations"):
    if name not in observations:
        raise SystemExit("candidate evidence publication is incomplete")
if "foreign_resource_canary" not in report["assembly"]["inputs"]:
    raise SystemExit("candidate assembly canary is missing")
PY

CPK_CANDIDATE_EVIDENCE_ID="$EVIDENCE_ID" \
    sh "$ROOT/scripts/docker_residue_audit.sh"

python -m scripts.cpk_server_candidate_lifecycle success \
    --ledger "$LEDGER"
SUPERVISOR_CLASSIFICATION=passed
supervisor_cleanup
trap - EXIT HUP INT TERM
