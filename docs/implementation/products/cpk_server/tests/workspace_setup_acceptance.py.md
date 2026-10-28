Source: [workspace_setup_acceptance.py](../../../../../products/cpk_server/tests/workspace_setup_acceptance.py).

The existing owning Docker gate runs this composition inside its disposable
PostgreSQL schema fixture. Actual admitted input enters the #346 initializer,
then the current process parser/verifier/startup guard and real public HTTP
handler. PublicHttpTransport retains its route and query encoding; its urllib
opener bridges to TestClient, and readiness uses a socket seam. There is no fake
permission store or command response.

The positive case checks complete enrollment and actual registration binding.
Missing provider scopes and a stale management revision must reach real 403/409
responses with earlier acknowledgements preserved. Public revocations precede
normal factory reconstruction; permission and assignment revisions remain revoked,
ordinary access stays denied, and tripwires forbid startup initialization/setup.
Provider interpreters are explicitly disabled, so this is HTTP/PostgreSQL
composition, not provider execution, Docker acquisition or published-image proof.

On an unexpected positive-case stop, the fixture prints only bounded HTTP status
integers, acknowledged-command count and closed pending/last-read route IDs.
Private target identities, credentials, keys and response bodies are excluded.
This diagnoses actual reach without weakening the production error boundary.
