Source: [test_operations_application_factory.py](../../../../../products/cpk_server/tests/test_operations_application_factory.py).

## #341 factory and startup targets

The new targets use actual Operations owners through the shared factory and
HTTP boundary. A failing UoW port proves non-administrators are denied before
store access and unavailable administration/current-workspace reads remain
bounded 503 responses. Configuration targets reject mismatched installation
policies and competing static authority. Startup targets require the existing
installation receipt before provider/effect composition and redact failures.
The existing static sharing/delegation tests remain unchanged.

These targets are unvalidated. The configuration interface is currently absent,
so its assertion is expected to stop each target before deeper behavior; that
must not be reported as evidence for unreached assertions. The real PostgreSQL
public enrollment/revocation witness is separate and uses the ordinary smoke.

These existing tests preserve shared UoW, clock, ID domains, lifecycle/fold/start,
runtime/ingress and observer owner composition, plus production/witness delegation
to the same factory. #315 extends the exact service-map keyword premise with
delegation_key_generation and requires its default value to remain None. All
previous sharing and no-construction-IO assertions remain. The four optional-input
cases and explicit authority forwarding live in test_delegation_generation_composition.
No durable algorithm or provider acceptance is implied by these wiring tests.

#317 adds secret_material_provision to the exact service-map keyword set and
asserts its default None in the existing no-custodian case. This additive fixture
translation preserves all shared-owner, clock, ID and no-construction-IO laws.
The new custody/authority target matrix and independent-policy denial remain
unchanged from the reviewed causal-red checkpoint; normal green is pending.
