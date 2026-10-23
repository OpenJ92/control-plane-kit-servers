Source: [test_managed_native_connection.py](../../../../../products/cpk_server/tests/test_managed_native_connection.py).

The existing tests exercise the concrete managed native observation bridge and
its process-factory composition. #315 changes only its provider double to declare
delegation_key_generator=None, preserving unavailable generation while the real
effect-port factory runs. Existing observation and owner-wiring assertions remain
unchanged; this fixture does not claim connected-provider or generation acceptance.

#317 also declares secret_custodian=None on that same provider double, preserving
unavailable provision in this native-observation fixture. CI40030724535 ran615
CPK methods: all three new provision composition methods passed, but this method
stopped at the real effect-port call because the double omitted the custody field.
Its later native bridge, no-fallback and no-transaction assertions were unexecuted;
the correction retains them unchanged. Production and protected-input target laws
are unchanged. The later integrated witness and full gate remain unverified.
