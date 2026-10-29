Source: [test_operations_application_factory.py](../../../../../products/cpk_server/tests/test_operations_application_factory.py).

## #341 factory and startup targets

The new targets use actual Operations owners through the shared factory and
HTTP boundary. A failing UoW port proves non-administrators are denied before
store access and unavailable administration/current-workspace reads remain
bounded 503 responses. Configuration targets reject mismatched installation
policies and competing static authority. Startup targets require the existing
installation receipt before provider/effect composition and redact failures.
The existing static sharing/delegation assertions remain unchanged.

At the test-only checkpoint, the configuration interface was absent. The
corrected red run reached that assertion before deeper behavior; it provides
no evidence for unreached assertions. The real PostgreSQL public enrollment/
revocation witness is separate and uses the ordinary smoke.

Corrected run40582892453 passed integrity and reached the absent-configuration
assertion in all three new targets; deeper assertions remained unreached. The
implementation preserves those targets. The existing entrypoint delegation
fixture now explicitly sets its Mock configuration's workspace_authority to None
for its static intent; production does not special-case Mock objects.

The review-found default-clock regression has a focused test constructing and
round-tripping an actual WorkspaceAdministrationReceipt using the factory's
default clock. It exercises the owning public timestamp contract rather than
matching a clock helper's text. Existing explicit-clock forwarding stays tested.

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
## #351 disabled-default fixture

The existing production-delegation mock explicitly disables provider-policy
authority, preserving its shared-factory assertions as the optional typed field
is added. Real provider-policy composition laws are exercised in
`test_provider_policy_composition.py`; owner algorithms remain upstream tests.
