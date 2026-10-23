Source: [test_operations_application_factory.py](../../../../../products/cpk_server/tests/test_operations_application_factory.py).

These existing tests preserve shared UoW, clock, ID domains, lifecycle/fold/start,
runtime/ingress and observer owner composition, plus production/witness delegation
to the same factory. #315 extends the exact service-map keyword premise with
delegation_key_generation and requires its default value to remain None. All
previous sharing and no-construction-IO assertions remain. The four optional-input
cases and explicit authority forwarding live in test_delegation_generation_composition.
No durable algorithm or provider acceptance is implied by these wiring tests.
