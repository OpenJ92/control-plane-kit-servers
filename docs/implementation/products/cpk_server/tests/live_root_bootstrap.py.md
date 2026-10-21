Source: [live_root_bootstrap.py](../../../../../products/cpk_server/tests/live_root_bootstrap.py).

#301 extends the existing prepare stage with an offline commissioning witness
inside the actual bootstrap driver built by unchanged test.sh. A subprocess uses
only the image's CPK, gateway and Secrets product paths, checks product module
origins, prepares two isolated fixture keys, decodes both actual receiving
artifacts and verifies completed reuse. It emits one fixed public success line;
private output or caught child errors are not printed. Temporary fixture custody
is removed by its owning temporary-directory context and never enters ordinary
bootstrap material.

This is a source packaging witness, not production image qualification or new
receiver-protocol acceptance for the historical CPK/Secrets images. The existing
real launcher plan/apply/public setup, numeric identity/socket observation,
denial/no-redispatch and exact owned cleanup behavior is preserved. Historical
limitations in those observations remain unchanged.
