Source: [managed_native_material.py](../../../../../products/cpk_server/tests/managed_native_material.py).

The fixture compiles genuine fresh and retained graph pairs and registers typed
product/runtime inputs. Its original hand-built request and synthetic typed
installation proof remain available for existing composition tests.

The #225 `lowered_request` helper instead calls the same Operations pure lowering
used by the coordinator, then Core's request binder. It does not read or copy the
hand-built request's product material. It supplies explicitly authored token
reference/version inputs, not generated ingress ownership or admitted history.
Operations owns the separate real coordinator/database proof of those facts.
