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

#354 adopts accepted Secrets E and replaces the historical three-value initializer.
Inside the initializer, the protected credential document is parsed once; that
same tuple seeds `admit_provider_custody` and becomes the returned credentials.
The fourth value is the owner's real `ProviderPolicyStore`, bound to the same
admitted database path and provider identity. Existing exact workspace/intents,
encryption, audit, denial and cleanup behavior remain; no policy-admin capability,
raw SQL seed, tuple fallback or mirrored policy state is introduced. Existing
protected-input integration assertions remain the consumer laws. The normal
Docker gate owns compatibility; G #342 retains same-process policy/retained-upgrade
proof, which this in-process bridge does not establish.
