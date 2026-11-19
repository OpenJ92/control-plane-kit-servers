Source: [components_acceptance.py](../../../../../products/cpk_server/tests/components_acceptance.py).
Maintain alongside its source.

This bounded witness is called by the existing workspace-authority acceptance
scenario inside the ordinary Servers Docker gate. It uses the real restarted
factory, configured credential verifier, dynamic permission resolver and isolated
Operations PostgreSQL stores; it does not mock product queries or durable facts.

Public commands create a separate workspace, grant the exact operator scopes,
and register two descriptors. HTTP/MCP reads traverse two pages with an opaque
scope-bound cursor and inspect exact descriptor digests. Results retain the
backend-issued ProductReference and noncanonical display label. V2 required-only
and mixed embedded/required slots appear as declared configuration slots, without
default-origin or readiness inference. File/environment/secret-handle canaries
and credentials must not appear in responses.

The same public surfaces prove denied-before-grant, foreign-workspace refusal,
malformed/foreign cursor and limit errors, malformed/missing digest detail and
invalid credentials. Existing schema cleanup owns the disposable records. No
provider, image fetch, deployment, or Library authority is introduced. This is
application adapter composition evidence only once the owning gate executes it;
the standalone recording-service host test proves mapping, not durable semantics.

Query arguments use `urlencode(..., quote_via=quote)`, matching the maintained
client and existing workspace-authority fixture. Default form-plus encoding of
JSON whitespace was invalid under the strict percent-decoded query contract;
the aligned host-test failure exposed the same defect here before this witness
was reached. Paging, rejection assertions and production decoding are unchanged.
