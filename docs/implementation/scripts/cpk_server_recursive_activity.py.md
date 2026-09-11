Source: [scripts/cpk_server_recursive_activity.py](../../../scripts/cpk_server_recursive_activity.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This legacy recursive controller creates a fixed parent workspace, registers
local Docker authority and delivery, imports CPK/Postgres descriptors and drives
plan/approval/admission/claim/start/execute/advance over public HTTP/MCP routes.
The frozen ClaimedRun and result decoders come from the hosted controller.
A maximum 140 execute calls bounds one parent run; failed/unsupported/uncertain/
blocked results stop it. Optional local chain depth is one through ten, with
each deeper level delegated to HostedWorkflow.

Each child graph connects all four store requirements to one Postgres node.
The harness creates a distinct local product identity by adding secret
environment deliveries for nested local-development material and legacy
Docker-config selectors. This changes contract data without rebuilding the
referenced image. Current bootstrap rejects those legacy selectors. The initial
health check also expects runtime none at depth one although the builder starts
from the Docker descriptor; this is not fresh current-source acceptance.

The controller itself has ambient Docker effects: it scans network-name prefixes
and connects itself/parent/children for reachability. It finds a child by a unique
workspace/node label match and returns its name, not immutable exact-run custody.
These side effects sit outside the public operation history and have no local
rollback journal. Shell cleanup owns final fixture disposal.

Parent assertions select created/health event payloads and image/name patterns;
deeper assertions require a matching successful step. They do not establish
image provenance, every health property or restart retention. Direct JSON health
reads use bounded reads/retries but no exact full-document or oversize sentinel
contract. The outer sanitized main suppresses ordinary exception text; helpers
and delegated process logs are not a universal redaction boundary.

Related source: [launcher](cpk_server_recursive_activity_smoke.sh.md),
[hosted workflow/decoders](../../../scripts/cpk_server_hosted_activity.py),
[process admission](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md),
[fixture assertions](../../../products/cpk_server/tests/test_image_bootstrap.py).
