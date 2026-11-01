Source: [managed_native_material.py](../../../../../products/cpk_server/tests/managed_native_material.py).

The fixture compiles genuine fresh and retained graph pairs and registers typed
product/runtime inputs. Its original hand-built request and synthetic typed
installation proof remain available for existing composition tests.

The #225 `lowered_request` helper instead calls the same Operations pure lowering
used by the coordinator, then Core's request binder. It does not read or copy the
hand-built request's product material. It supplies explicitly authored token
reference/version inputs, not generated ingress ownership or admitted history.
Operations owns the separate real coordinator/database proof of those facts.

The new lowering witnesses opt into registered participants: the existing product
builder declares the API application configuration slot and the connector's
explicit token delivery before compiling/registering the graph. Operations'
retained participant guard requires those node inputs to match their registered
contracts. The default interpreter-only fixture remains unchanged. The first
old-pin run exposed these two incomplete premises before retained lowering;
those setup errors are not causal evidence for the missing material defect.

This opt-in mode also uses Operations' canonical protected token-file path before
constructing the descriptor, node and synthetic original-installation proof.
The sole delivery already has the required type, tunnel-token intent,
owner-read-only mode, TUNNEL_TOKEN_FILE binding and typed reference; version
selection stays unchanged. The accepted-pin run first exposed the path mismatch
before reader assertions. Its failed evidence remains recorded; this correction
changes the helper's input bytes from the earlier causal-red checkpoint while
preserving every test assertion and the default interpreter-only path.
