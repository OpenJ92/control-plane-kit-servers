Source: [protected_input_preparation.py](../../../../../products/cpk_server/tests/protected_input_preparation.py).

#317 adds one unconditional preparation witness to the existing smoke controller.
The normal repository Docker gate already owns its PostgreSQL and container
lifecycle. IsolatedOperationsSchema owns creation and verified deletion of the
unique schema; psycopg's conninfo encoder supplies the same schema-only search
path to every actual CPK store setting. A current-schema assertion precedes host
construction. The real host installs its schema and constructs its own UoW and
Operations factory. No store, service map or factory is replaced.

Only the existing provider transport seam points to the real encrypted Secrets
fixture. Credential authentication and separately configured authority are real.
Operator preparation scopes, viewer reads, individual generation/provision/
registration scopes and worker kind remain distinct. Refusal observations compare
actual provider invocation lists as well as audit rows. Missing-dependency 501
and independent current-policy tests stay in the companion factory suite.

Authenticated commands create the workspace/provider registration, generate the
three required signing families, provision synthetic external material, activate
keys, read real verifier/context output, import source products, register runtime
and ingress authorities, and prepare a complete declared Hello/gateway/connector
graph. The generated public keys feed verifier/artifact construction; status reads
retain the returned custody versions. The admitted external reference feeds the
ingress authority. No private material or receipt/admission record is seeded.
This does not invent version pinning on an ingress-authority contract that accepts
a reference. A later runtime grant remains the Operations owner's responsibility.

The duplicate provision is an explicit conflict test, not a retry policy. Its
reference-only status navigation is checked with a separately authorized viewer;
denied calls, duplicate/status reads and HTTP/MCP refusals cause no provider work.
Bounded public receipts, graph, plan, session, run-list and audit observations
reject synthetic material, encoded material, bootstrap credentials and private
keys. The preparation must require approval, reject this operator's approval and
execution requests, have no activity runs, and preserve current graph/projection.
No runtime/cloud deployment or secret resolution is performed.

The fixture does perform test-owned provider generation/provision and encrypted
durable custody. Context cleanup removes its schema and protected temporary
files. It does not use retained user credentials, tunnels or DNS. It does not prove
TLS/network behavior, published images, native execution or public/live acceptance.

This is an unexecuted test-only checkpoint. The package-level missing-port tests
may stop the normal fail-fast gate before this integration witness; only reached
assertions can receive causal-red credit. Production enablement follows that red
evidence and independent review, never this fixture's existence alone.

Concrete source review corrected two fixture expectations before any execution:
MCP intake asserts the accepted exact 404/unknown-operation refusal, and key
activation supplies issuer/key ID explicitly as URL coordinates as well as its
existing command fields. The HTTP helper still does not infer URL coordinates
from confidential payloads. Production and the governing #316 tests are unchanged.
