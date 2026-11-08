Source: [protected_input_provider.py](../../../../../products/cpk_server/tests/protected_input_provider.py).

The #317 fixture runs the actual Secrets API, credential loader, encrypted store,
custody admission and audit owner. It creates protected synthetic bootstrap files
inside one temporary directory. Root/provider wrapper keys only admit those
apps; #317's managed keys are generated through authenticated CPK/provider APIs.
Provider grants name one test workspace and explicit generation/write intents;
metadata is workspace-wide as the accepted provider contract defines.

The synchronous httpx transport forwards actual method, URL/query, headers and
request body to a context-managed real provider TestClient, returning its actual
status/headers/bytes. Unknown destinations fail, with no network fallback or
synthetic receipts. Per-request client closure cannot close the provider; the
outer context owns its lifetime. Observations retain bounded public method/path
pairs, never authorization or request/response bodies. Cleanup closes the client
before deleting the test custody directory, including entry failures.

The normal integration witness performs real test-owned encrypted custody
effects, not external provider/TLS validation.

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
The metadata grant explicitly carries `intents: []`: metadata is intentless in
the accepted owner. Omitting the field means wildcard, not an empty coordinate.

Optional workspace/write/resolve inputs now support #163's separately authorized
imported-key fixture. Defaults retain #317's exact grants and generation behavior.
An optional provider identity likewise binds custody, policy and the actual app
to the selected graph's existing reference provider, retaining `input-provider`
as the default. It does not remap the graph or forge metadata across providers.
No wildcard scope, policy-admin capability or generation expansion is introduced.
The retained TestClient lets that caller import ephemeral matching material and
confirm its exact version through normal authenticated Secrets write/resolve.
Its ordinary CPK register/activate/readback belongs to the source registration
fixture. Custody, authentication, durable policy and directory cleanup stay real;
these imports are not production keys or original-run signing authority by themselves.
