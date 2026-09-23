Source: [gateway_diagnostic_fixtures.py](../../../../../products/cpk_server/tests/gateway_diagnostic_fixtures.py).
Maintain this companion with its source and selected contracts.

Synthetic, container-local fixture extends the actual three-artifact gateway source
contract with distinct transit/workload public keys and original bounded Core grants.
No credential is logged or retained as evidence. Recording UOW/store seams return
real registered values and invoke the real authorization/projection functions; they
do not implement SQL, isolation, durable rollback or a second authority engine.

First sourcea867d1f exposed a latent recording-authority fixture defect: the
provider prefix had no path and Core rejected its SecretReference before nine
deeper tests reached the adapter. The correction admits the two exact synthetic
transit/workload handles instead. This preserves source and assertions and narrows
the fixture provider admission; the failed run is not transaction/source-green.
