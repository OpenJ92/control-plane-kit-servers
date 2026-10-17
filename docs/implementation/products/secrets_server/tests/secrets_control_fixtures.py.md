Source: [secrets_control_fixtures.py](../../../../../products/secrets_server/tests/secrets_control_fixtures.py).
Maintain with the source file and actual service/Core/SDK contracts.

SourceControlAuthority constructs actual Secrets configuration/declaration with Core target/runtime and separate SDK public-key families. Private Ed25519 keys stay only in the owning process. Product value tests discard authority after obtaining public configuration; the numeric fixture retains it in controller memory for fresh typed static/health grants immediately before use. Grants last120 seconds, use explicit integer issued_at and random JTI, and are signed with PyJWT using actual Core descriptors and request digests. This fixture neither reimplements verification nor writes keys/credentials or creates services. HTTP/materialization/cleanup stay with the existing numeric owner. Initial red stopped before constructing this fixture; its new grant behavior awaits source/fixture review and full green execution.

#237 receiving target translation supersedes the old private control schema and
secret-shaped public path selector. Fixtures now return actual Core
ReceiverNodeControlConfiguration with full receiver identity and purpose-indexed
families. The single CPK_WRAPPER_CONFIGURATION_FILE binding is both public graph
configuration and source image input; private bootstrap names/modes and every
other historical runtime field remain unchanged. Source-contract equality removes
only the declared configuration/surface/capability/environment additions.

Synthetic receiver identity is deterministically scoped to the fixture run so
initial/restart file phases preserve it while keys change. This is test authority,
not a production identity allocator. Both generation and the independent checking
side choose the explicit source-authored/source-projection authority context;
it is never derived from a token or installed graph revision. Actual receiver V2
requests/grants/result codecs preserve original bounds, purposes and denials.
The original three generated files, modes, exclusive creation, log redaction and
exact controller-owned cleanup remain. No new phase or resource is introduced.

Only targets/fixture protocol translation changes here, before receiving product
implementation/dependency adoption. All original method identities remain. No
source-live run, restart acceptance or new canonical green is credited before
the unchanged whole owning gate. Existing accepted Secrets Z owns its service
implementation; Servers merely packages/adapts that public configuration.
