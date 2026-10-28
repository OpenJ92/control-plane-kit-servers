Source: [dynamic_setup_fixtures.py](../../../../../products/cpk_server/tests/dynamic_setup_fixtures.py).

The #347 fixture reuses #345's real plan/private commitment and admission. It
authors explicit self-grants and optional management intent, then writes only
the fixed protected setup files. Expected public values use actual Operations
receipt/record constructors. It implements no store, authorization transition or
permission state machine; real process/PostgreSQL composition remains separate.
