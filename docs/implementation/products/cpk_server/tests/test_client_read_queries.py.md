# Installed-client read-query targets — Servers #341

These unexecuted targets follow the reviewed process/client plan at
https://github.com/OpenJ92/control-plane-kit-servers/issues/341#issuecomment-6462015304.
They exercise PublicHttpTransport against the actual shared authenticated HTTP
boundary/application. Only the socket transport and existing recording service
are substituted; the test does not implement permission or pagination semantics.
The existing boundary fixture supplies authentication and service dispatch.

The client must preserve raw runtime/authority coordinates, structured full
identity/cursor text containing literal spaces and plus, integer limits, and
the existing receiver-authoring expected/pending_draft JSON fields. Invalid and
oversized percent-encoded queries refuse before credential reads or sends with
bounded errors and no payload-bearing exception context. A boundary authentication
refusal still reaches the existing client authorization error without a service call.

Imports of Servers values occur at test runtime because existing suites unload
those modules. Temporary credentials are synthetic fixture values. No host tests,
provider contact, durable policy state, live deployment or G lifecycle evidence
is established. First owning execution and independent target review are pending.
