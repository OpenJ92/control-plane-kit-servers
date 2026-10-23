Source: [test_managed_native_connection.py](../../../../../products/cpk_server/tests/test_managed_native_connection.py).

The existing tests exercise the concrete managed native observation bridge and
its process-factory composition. #315 changes only its provider double to declare
delegation_key_generator=None, preserving unavailable generation while the real
effect-port factory runs. Existing observation and owner-wiring assertions remain
unchanged; this fixture does not claim connected-provider or generation acceptance.
