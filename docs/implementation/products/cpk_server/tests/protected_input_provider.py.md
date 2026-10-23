Source: [protected_input_provider.py](../../../../../products/cpk_server/tests/protected_input_provider.py).

The #317 fixture runs the actual Secrets API, credential loader, encrypted store,
custody admission and audit owner. It creates protected synthetic bootstrap files
inside one temporary directory. Root/provider wrapper keys only admit those
apps; managed keys must be generated through authenticated CPK/provider APIs.
Provider grants name one test workspace and explicit generation/write intents;
metadata is workspace-wide as the accepted provider contract defines.

The synchronous httpx transport forwards actual method, URL/query, headers and
request body to a context-managed real provider TestClient, returning its actual
status/headers/bytes. Unknown destinations fail, with no network fallback or
synthetic receipts. Per-request client closure cannot close the provider; the
outer context owns its lifetime. Observations retain bounded public method/path
pairs, never authorization or request/response bodies. Cleanup closes the client
before deleting the test custody directory, including entry failures.

This is an unexecuted fixture checkpoint. The normal integration witness performs
real test-owned encrypted custody effects, not external provider/TLS validation.
