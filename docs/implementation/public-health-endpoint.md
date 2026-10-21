# Public managed health endpoint selection

Issue181 step1 tests the existing bridge's public/local transport boundary.
The target checkpoint has no application source change and is expected to fail
because public signed reads still inspect a private endpoint that they discard.

The exact selected Core fresh plan uses independent native connection and
authenticated management-path observations, followed by ingress readiness.
Retained edits keep their separate local-readiness law. These tests compile the
genuine fresh graph and preserve the complete canonical graph pair; they do not
filter operations or fabricate admitted execution history.

`test_managed_health_bridge.py` requires all three public forms (authenticated
path, gateway ingress readiness, workload health) to retain the exact original
request, authority, grants and self/workload route through NamedIngress without
a private read. The actual signed reader and public HTTP transport are also
exercised with ephemeral test keys and a failing HTTP transport, preserving
timeout/failure results and bounded redaction. No real DNS/HTTP or credential
service is used. Local endpoint failure still prevents signing-reader access,
and wrong current authority refuses public reads before either reader.

Selection still requires the existing scoped placement. This slice does not
enable ordinary process startup, remove retained-local requirements, qualify
remote Docker/TLS, attach a network, or establish live225 acceptance. Those
boundaries remain separately held. Validation uses unchanged owning Docker
`./test.sh` and the ordinary hosted workflow.
