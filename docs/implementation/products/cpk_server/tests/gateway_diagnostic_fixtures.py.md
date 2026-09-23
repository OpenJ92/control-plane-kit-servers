Source: [gateway_diagnostic_fixtures.py](../../../../../products/cpk_server/tests/gateway_diagnostic_fixtures.py).
Maintain this companion with its source and selected contracts.

Synthetic, container-local fixture extends the actual three-artifact gateway source
contract with distinct transit/workload public keys and original bounded Core grants.
No credential is logged or retained as evidence. Recording UOW/store seams return
real registered values and invoke the real authorization/projection functions; they
do not implement SQL, isolation, durable rollback or a second authority engine.
