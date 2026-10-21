# Public managed health endpoint selection

Issue181 step1 corrects the existing bridge's public/local transport boundary.
Only the exact GATEWAY_LOCAL_READY operation reads a private endpoint. Public
operations retain their selected NamedIngress and pass no local destination.
All original selection, authority, receiver, route and signing checks remain.

Corrected target476d82b established six intended private-read failures in
[owning run39521946962](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/39521946962),
independently confirmed by Kepler. The source delta is only the conditional read;
the reviewed target assertions are unchanged. Full source green and final review
remain pending; [PR289](https://github.com/OpenJ92/control-plane-kit-servers/pull/289)
records exact checkpoints and final disposition.

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
The transport connects to the DNS-authorized numeric IP while preserving the
authored hostname in Host and TLS SNI; all three values are asserted. The initial
target incorrectly expected a hostname URL and was corrected after independent
review, before application implementation.

Selection still requires the existing scoped placement. This slice does not
enable ordinary process startup, remove retained-local requirements, qualify
remote Docker/TLS, attach a network, or establish live225 acceptance. Those
boundaries remain separately held. Validation uses unchanged owning Docker
`./test.sh` and the ordinary hosted workflow.
