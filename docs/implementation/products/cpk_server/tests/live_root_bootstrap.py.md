Source: [live_root_bootstrap.py](../../../../../products/cpk_server/tests/live_root_bootstrap.py).

#301 extends the existing prepare stage with an offline commissioning witness
inside the actual bootstrap driver built by unchanged test.sh. A subprocess uses
only the image's CPK, gateway and Secrets product paths, checks product module
origins, prepares two isolated fixture keys, decodes both actual receiving
artifacts and verifies completed reuse. It emits one fixed public success line;
private output or caught child errors are not printed. Temporary fixture custody
is removed by its owning temporary-directory context and never enters ordinary
bootstrap material.

This is a source packaging witness, not production image qualification or new
receiver-protocol acceptance for the historical CPK/Secrets images. The existing
real launcher plan/apply/public setup, numeric identity/socket observation,
denial/no-redispatch and exact owned cleanup behavior is preserved. Historical
limitations in those observations remain unchanged.

SOURCE review found that the actual driver inherits the historical published CPK
image, not the current service Dockerfile. The witness now compares installed
Core/Operations/SDK/Interpreters/Secrets direct_url.json URLs and subdirectories
with the exact selected upstream manifest. Version 0.1.0/import success alone
does not prove cohort alignment. All legacy checks remain unchanged.

Run39666813360 passed all901 package tests but failed inside this child. Build
evidence showed same-version inherited dependencies were retained; the exact
child stage was unknown because imports precede provenance. The child now emits
only fixed ordered markers for imports, provenance, plan, prepare, decode and
reuse. The parent accepts an exact marker prefix on failure and reports its last
stage, or unknown for malformed output. No arbitrary child stdout, stderr,
traceback or payload is printed. Success still requires zero exit and the exact
success line, now preceded by all six markers. Three focused projection tests
cover every stage, malformed/private output and incomplete or failed success.

#302 adds a seventh closed stage, complete-plan, before the original success
condition. Using only image-owned bootstrap/frontend/product modules and the
same isolated public commissioning artifacts, it builds real source contracts
and compiles the complete four-node/two-binding/four-import profile. It verifies
both artifact descriptors survive exactly. A second fixed public success line
is printed only after the child passes every assertion. The synthetic website
image is never pulled or served. All original commissioning and legacy launcher
checks remain; this source packaging evidence cannot qualify production images.
# Managed PostgreSQL driver planning witness (#327)

The existing image-owned commissioning subprocess now verifies that PostgreSQL
authoring code is included in the actual driver and composes its managed contract
using an explicit fixture receiver and the existing public verifier families.
The old two-role commissioning output and exact reuse remain unchanged. Assertions
cover the projected public artifact, password file and absence of a published
PostgreSQL port. This is driver packaging/planning evidence, not managed-image
startup or published-digest qualification. The existing native acquisition and
separate PostgreSQL product readiness/storage witnesses retain their meaning.
