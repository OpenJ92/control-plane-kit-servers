# Finite gateway diagnostic setup (#221)

This entrypoint prepares the already reviewed self-health diagnostic. It does
not deploy a topology or supply public capstone acceptance. Its workspace's
initial graph is the empty graph returned by Operations; configuration artifacts
use that real revision without claiming that Operations deployed the gateway.

The executable module is
`control_plane_kit_servers_cpk_server.gateway_diagnostic_actions`. Each invocation
selects one of `prepare`, `generate`, `operations`, `artifacts`, `route-update`,
`seal`, or `route-restore` and requires `--approval /absolute/protected/file`.
This PR prepares source; it grants no live mutation authority.

## Approval and source delivery

The operator supplies a separately mounted, owner-protected JSON approval outside
the run directory. Its closed fields are `profile` (`cpk221-approved-setup.v1`),
`source_sha256`, `root` (`/private/tmp/cpk221-self-health-r1`), integer `expires_at`,
`phases`, `resource_plan`, `controller_image_digest`, `gateway_image_digest`,
`runtime_id`, `ingress_receipt_file`, and `cloudflare_credentials_file`.
The source digest is the exact reviewed module's SHA-256. Image coordinates,
runtime identity, phase scope, credential/receipt mounts and resource-plan identity
come from the final operator-reviewed execution packet. The candidate diagnostic
packet never supplies these inputs. Protected filesystem provenance is the trust
boundary; this is not a new approval service or a cryptographic user signature.

Reuse controller `sha256:b6ef78256a9491270902133350dccab4fcf1dbdbfa8a16b2fe542ae9bcb1d7e4`,
built from Servers `369b3a3e2ad497ac4ab75e0c51ad11cb68dc1c0e` and the selected
dependency pins. It does not already contain this module or Stage A admission.
Deliver both reviewed files read-only, with their exact hashes in the execution
packet. Extend the installed CPK package's module search path to that directory
for these new names only; retain installed existing owners. Do not shadow the
entire frozen package or claim new files came from the frozen source image.

CLI output contains only phase and categorical status. It never prints receipts,
provider bodies, credentials, private origins, database URLs or exception text.
The final `seal` produces a single canonical runner packet, then derives its
separate trusted bindings and digest approval inside the previously approved
scope. It cannot reseal/retry an existing packet or renew an expired grant.
Sealing refuses before writing any packet/authority files when less than the
full 300-second grant window remains on the original approval. Tests join the
generated seal to the actual runner authority loader and approval validator.

## Owner composition

`prepare_private_material` exclusively creates a 0700 run directory and 0600
files. Provider generation and resolution have different credentials, each with
one exact action, one workspace, and the two health intents. Setup and runner
operators also have distinct credentials; independently retained binding files
prevent changing a presented token from changing its authority. Three startup
verifiers keep public halves only. Private halves are never serialized; no
claim of Python memory erasure is made.

`generate_health_keys` sends exactly the two original provider API requests.
The selected Secrets owner generates and audits private keys. Validation binds
closed public response fields, reference, canonical secret ID, original purpose,
issuer, correlation, labels, active original version, actual Ed25519 material,
and fingerprint. Unknown/private-bearing responses stop the phase. Provider
credentials are not Operations signing grants, and the old probe-only generation
service is not repurposed.

`initialize_operations` authenticates with the existing verifier and applies
the existing route authorization policy before opening the schema connection or
any UOW. Setup has HUB_INSTANCE_CREATE, SECRET_PROVIDER_REGISTER,
DELEGATION_KEY_REGISTER and DELEGATION_KEY_ACTIVATE; runner has only
SECRET_PROVIDER_USE. The new database must have the exact identity and no public
tables. Existing schema, workspace, provider/reference and key registration/
activation services own their transactions. Their actual returned identities are
retained. Independent service commits are not an atomic setup transaction.

`build_artifacts` composes actual gateway control/transit/relay factories, selects
the gateway's own control provider at 8000, and uses the actual product codec.
The local source image coordinate is explicitly diagnostic, not evidence of a
published registry manifest. `seal_packet` uses actual Core paired grants and
the existing diagnostic decoder; its validity window is at most 300 seconds.
Seal only after route readiness and the separately reviewed unsigned denial
observation. No alternate attempt or automatic retry is provided.
Those readiness/denial prerequisites are enforced by the fixed external
execution order and retained gate evidence, not by this module itself.

## Tunnel change and restoration

Stage A observed a compatible retained HTTP origin on port 8080 and no active
connections. Frozen gateway production startup requires 8000. Each change reads
fresh config/connections, requires the exact retained hostname and expected
origin, and preserves the complete validated original config privately. Only
the service port changes. Both PUT response and subsequent GET must agree.
The hostname forwards **all matching paths** to this gateway, not just readiness.

The adapter uses the existing Cloudflare API client for authentication and
provider error semantics. Its transport permits only config GET/PUT and
connections GET for the exact retained tunnel. No token, DNS, deletion, redirect,
proxy or retry endpoint is available. HTTP uses a 10-second I/O timeout, bounded
64-KiB uncompressed responses, and a 20-second elapsed check. These are not a
hard wall-clock deadline; the execution packet also provides external supervision.

Exclusive receipts claim each write before dispatch. Original/temporary config
digests, stage timestamps, and observed provider version when present are private
evidence. Completion preserves pending-stage history. Lost responses, malformed
PUT results and mismatching GETs retain pending status and refuse another send.
Restoration also requires zero active connections and exact current temporary
config; it restores the original complete snapshot once and verifies it.
There is no atomic provider CAS or distributed lock: the approved single-writer
window and remaining read/write race must be explicit. Concurrent drift or any
uncertainty stops instead of overwriting another writer.

## Resource delivery and retention

Preparation, setup and runner use host UID501:GID20; products preserve gateway
UID10005 and Secrets UID10006. Public configs may be delivered read-only 0444
after classification. Private host inputs remain 0600. At the separately
Docker-authorized orchestration boundary, existing
`DockerSdkClient.materialize_secret_file(..., owner_uid=10006)` delivers the new
master and provider credentials to named fresh volumes
`cpk221-self-health-r1-secrets-master` and
`cpk221-self-health-r1-secrets-credentials`, mounted via `content` subpaths.
Each delivery creates/removes a finite network-disabled helper; pin its image
explicitly to the reviewed controller. Do not silently pull the SDK default.
Setup/runner do not receive the Docker socket. Any new password-file delivery
volume must be separately named in the final resource ledger.
Mount only the runner's named files at the absolute paths recorded in its
bootstrap, never the entire setup directory containing the master, generation
token, setup bindings or provider credential document.

Keep delivery volumes, fresh database, Secrets custody/master and audit receipts
after owned runtime container/network cleanup. Preserve old tunnel, DNS, token,
old volumes and parent Secrets. No retained bootstrap adoption, broad cleanup,
schema reset, automatic compensation or rollback of key/audit records occurs.

## Tests and evidence limits

Target review passed at `10ebeb8` (PR224 comment5804758490). Ordinary CI
35934581532 established 15 missing-interface failures, zero errors, with 290
existing CPK tests green; log SHA-256
`f3739aa53574f828923bb279bb2969214ee91c2b27d11527e3b4b8043d7fb33e`.
The real selected Secrets API/custody fixture proves scoped generation composition.
Service spies prove authenticated command wiring and partial receipt retention;
they do not prove real Postgres lifecycle or transaction isolation. One synthetic
receipt fixture was corrected to 0600 after the production protected-file reader
correctly refused its default 0644 mode. Its behavioral assertion was preserved.
Route recording and real bounded-adapter tests prove dispatch/verification laws,
not provider mutation acceptance. Final ordinary package CI and independent source
review must pass before the executable packet is presented for live approval.
