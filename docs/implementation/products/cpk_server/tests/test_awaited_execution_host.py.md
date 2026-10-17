Source: [test_awaited_execution_host.py](../../../../../products/cpk_server/tests/test_awaited_execution_host.py).
Maintain this companion alongside its source and actual selected Operations contracts.

Servers231 tests the real create_app HTTP/MCP host, actual process credential
extraction and static-development multi-principal verifier, real Operations
application/execution service and its typed command constructors. Only the
effectful Operations factory and coordinator entrance are replaced. Ephemeral
test credentials and the existing SDK control fixture remain local to the test.

The causal entrance guard requires async process-boundary methods before setup;
it distinguishes missing dispatch from failed imports, database setup or Docker
apparatus. The targets require awaited execute/reobserve completion, identical
trusted actor/workspace/fence meaning, no synchronous execute, permission and
workspace denial, closed reobserve framing, Operations numeric refusal, bounded
malformed/oversized/internal failures and cancellation reaching the awaited port.
Tests use events to observe in-flight work; cleanup cancels any outstanding task.

Recording coordinator calls establish only this transport/service join. They
do not prove persistence, attempt folding, current-authority reload, signing,
provider effects, image support or cleanup. Those remain with Operations and
later181/188/225 acceptance. The ordinary Docker-backed test.sh is the sole
executable gate; existing host/SDK/neutral-boundary tests remain unchanged.
