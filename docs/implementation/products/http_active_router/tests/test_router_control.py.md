Source: [test_router_control.py](../../../../../products/http_active_router/tests/test_router_control.py).
Maintain with the product's protected receiving and forwarding laws.

Focused tests preceded implementation at commit a3b1412. They were not executed
as a compulsory red harness. The source/design packet on Servers185 establishes
law provenance; subsequent additions resolve actual Core codec context and
product test isolation without weakening behavior.

Test-owned Ed25519 fixture authority signs actual Core grants; no deployable key
is committed. The installed real stdlib host demonstrates successful static and
canonical liveness reads, authentic undeclared canonical readiness refusal and
representative authority/reserved-path denials before any forward call. Ordinary
/health/ready still forwards application Authorization. Two hosts demonstrate
key/settings isolation and no ambient fallback for an explicit empty mapping.

Receiving tests cover real artifact/contract codecs, complete historical policy
and unchanged source-contract fields, closed malformed/duplicate input, opened
regular-file identity, byte limits, symlink/FIFO/directory denial and fixed error
chains. Lifecycle tests exercise passive install and closure on each stage failure,
production port policy and serving interruption. Forwarding tests preserve the
five-second timeout, header filtering, 1MiB response boundary, error status/body
and no redirects. They do not reproduce the SDK's parser/admission matrix.

The existing descriptor suite deliberately evicts product imports. Each new test
refreshes its local module references so nominal configuration types remain from
the same loaded product generation. Pure imports are checked in an isolated
subprocess inside the owning test container. Test hosts use bounded HTTP reads,
external-thread shutdown/join and worker/socket closure. Only ./test.sh supplies
executable evidence; local/source tests do not prove image or public acceptance.
