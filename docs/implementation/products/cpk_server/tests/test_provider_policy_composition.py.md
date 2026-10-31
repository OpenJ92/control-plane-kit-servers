Source: [test_provider_policy_composition.py](../../../../../../products/cpk_server/tests/test_provider_policy_composition.py).

New-law Servers composition tests exercise the real shared factory, Operations
adapter/owners and fixed Interpreter client using synthetic credential files and
httpx MockTransport. They prove HTTP/MCP parity, independent identity admission,
zero construction on denial/malformed arguments, closed query framing, lazy
assembly, disabled/missing bindings, bounded failures, installer file admission
and production bootstrap forwarding. A minimal store-protocol fixture supports
command dispatch without recreating persistence/CAS tests. Replaced binding
triples deny historical reads/reconciliation without provider calls.

These tests do not establish provider-live, durable process or release acceptance.
No separate runner or synthetic target-red claim is introduced; the existing
Docker-backed repository gate owns execution. Validation is pending at this
source checkpoint.
Review corrections add real provider-only environment/verifier/application
composition with zero workspace grants and ordinary workspace denial, for both
static credential forms. Changed logical/provider identities are checked against
the original nonempty binding registry, separately from missing-binding tests.
Reconciliation coverage proves resolved-command no-redispatch and replaced-binding
denial; ambiguous provider readback remains upstream and process-acceptance evidence.
