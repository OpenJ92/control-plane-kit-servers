Source: [test_cpk_receiver_shell.py](../../../../../products/cpk_server/tests/test_cpk_receiver_shell.py).
Maintain with the #163 focused smoke's resource ownership and cleanup boundary.

These tests execute only inside the owning Docker test phase, with no Docker
socket. Finite fake CLI replies prove that a colliding run or receipt directory
cannot build or delete resources, a failed absence query cannot permit a build,
a failed removal readback remains unverified, and a changed source after build
stops before fixture startup. They check shell effects and public receipts,
without recreating Core/Operations state machines or proving real Docker cleanup.

Retained-diagnostic regressions additionally require that another digest is
refused before daemon access and that a colliding retained run cannot build or
delete resources. The ordinary image-mode collision/readback tests remain.
