# Gateway self-health operator diagnostic (#221)

This source-only tool is separate from admitted deployment and grandparent #163
acceptance. Its live prerequisites remain unverified. Local Docker was unreachable
at preparation; no resource or protected-state mutation was performed.

Inside the reviewed Servers controller image:

```
python scripts/gateway_self_health_diagnostic.py plan --packet /run/diagnostic/packet.json --artifacts /run/diagnostic/artifacts
python scripts/gateway_self_health_diagnostic.py run --packet /run/diagnostic/packet.json --artifacts /run/diagnostic/artifacts --bootstrap /run/diagnostic/bootstrap.json
```

Do not execute run before an exact source/image/resource/custody/action plan is
approved. The commands intentionally contain no credential, DSN or private origin.
The invocation must select readonly mounts and exact owned resources; this tool
does not launch or clean up resources. Preserve retained tunnel/DNS/token and all
unrelated resources. Retain committed authorization rows after cleanup.

Public artifacts use fixed filenames: control.json, transit.json, targets.json,
product.json. The canonical packet's closed fields are profile
`gateway-self-health-diagnostic.v1`, attempt_id, request, ingress, target_id,
transit_socket, source_commit, image_digest, resource_plan, artifacts (SHA256 of
each public input), transit_grant, workload_grant and two keys (transit first).
Each key identifies registration_id, key_id, fingerprint, private_reference,
reference_registration_id, provider_registration_id, endpoint_reference and
credential_reference. These are expected inventory references, not authority.
The grants are original Core codec values with fixed, identical short windows.
Expected target/readiness/runtime/context is checked against the actual artifacts.

The protected bootstrap file contains workspace_id, database_identity,
database_dsn_file, operator_credential_file, principal_bindings_file, approval_file,
secret_endpoints and secret_credentials. All private paths are absolute; private
files require root/current ownership and no group/other permission. Readonly mount
and parent-directory integrity are operator responsibilities. Do not treat arbitrary
writable caller setup as approved. Principal bindings are an independently reviewed
list of issuer, subject, kind, workspace_grants and credential_file; workspace grants
contain workspace_id and scopes. Existing local-development verification authenticates
the supplied credential. Packet-provided principal/scopes are rejected.

The separately protected approval contains packet_digest, issuer, subject,
workspace_id, attempt_id, database_identity, expires_at and reference. Its canonical
packet binding also fixes source/image/resource plan, artifacts and key inventory.
Materializing or changing this trusted approval/setup requires the concrete action
approval; merely constructing it does not grant permission. Actual existing database,
workspace, active delegation keys, provider/reference admissions and Secrets policy
must already be established. This tool never installs schema or registers custody.

Run locks stable attempt/family correlations, refuses either prior authorization,
uses the real Operations authorization producer twice, requests commit and exits
successfully before any key resolution. It then checks cancellation and approval,
signs once and dispatches once through default public DNS/HTTPS. No retry or renewal
follows ambiguity. Two committed rows consume the invocation even when no health
request follows; a new attempt requires a new explicit decision/approval.

Output separates offline plan, authentication/admission refusal, prior attempt,
commit uncertainty, authorized-not-dispatched and actual transport/health result.
Only received correlated HEALTHY passes readiness. Authorized-not-dispatched can
follow Secrets resolution; it does not imply zero provider I/O. Rows are authorization
evidence, never proof of sending or durable deployment completion. Cancellation
propagates while committed audit remains. An unsigned denial request is separately
planned and authorized; its status alone cannot prove zero target I/O.

Canonical dependency adoption uses accepted Interpreters388 with Coreb79,
Operationsbc559, SDK2c5 and Secrets827. It does not downgrade current e074 work or
change published image coordinates. Normal owner CI verifies installation; this
source recipe and fake-free public transport configuration do not prove live TLS,
resource ownership, protected key availability or execution success.
