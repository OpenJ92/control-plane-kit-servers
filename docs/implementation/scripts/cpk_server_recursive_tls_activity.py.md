Source: [scripts/cpk_server_recursive_tls_activity.py](../../../scripts/cpk_server_recursive_tls_activity.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This legacy two-level controller uses HostedWorkflow to deploy a local
CPK/Postgres child, registers a remote Docker TLS authority inside that child
using secret references, then requests one through ten grandchild CPK/Postgres
pairs on that authority. Four store requirements still converge on each paired
Postgres instance.

Harness product identities add local secret/legacy Docker-config deliveries
to the child contract. Grandchild product identities deliberately replace
verification with an empty VerificationContract because outer-network health
probing is unavailable. A successful step mentioning a grandchild therefore
does not establish its database/application readiness. Neither variant attests
new image bytes or releases production contract changes.

Authority list/detail checks verify selected public visibility and absence of
named TLS reference/private-key markers, not certificate usability or full
redaction. Authority use/admission remains with the actual server/interpreter.
The controller also uses ambient Docker to connect parent, itself and DinD to
matching network-name prefixes; those fixture reachability effects are not
public operation records or exact-run resource custody.

There is no controller-owned teardown, restart/history-recovery proof or durable
resume journal. The shell owns cleanup. Current bootstrap compatibility of
legacy material/verifier settings must be assessed separately from the source's
intended scenario. Sanitized main bounds ordinary final failure text, while
helper responses/logs retain their own limits.

Related source: [launcher](cpk_server_recursive_tls_activity_smoke.sh.md),
[hosted workflow](../../../scripts/cpk_server_hosted_activity.py),
[process admission](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md),
[fixture assertions](../../../products/cpk_server/tests/test_image_bootstrap.py).
