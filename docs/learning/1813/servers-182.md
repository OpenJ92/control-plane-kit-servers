# Gateway self-health source handoff (#182)

PR218 completes the gateway source contract after #180 relay and #147 transport.
The product now composes actual SDK surface/health verification with local
configured-and-serving readiness, independent of targets, connector and ingress.
One required public `gateway-control` artifact supplies its own exact identity
and verifier families beside transit trust and relay target configuration.
The serving lifespan resets readiness in `finally`, including exceptional exit.

The complete three-artifact source contract declares the real SDK surface and
replaces its two independent legacy HttpChecks with that managed observation
obligation. The actual Core compiler consumes the unchanged contract and requires
GATEWAY_LOCAL_READY before connector, authenticated path and workload progress.
No fixture-only surface, stripped check or synthetic ready result supplies proof.

The design rejected recursive downstream readiness and extra helper/exec paths.
Review found the need for a causal exceptional-lifespan test: a TestClient body
exception did not prove entry into the application's async exit. Corrected target
`3eb6082` directly enters that context and predates source `77cf8e4`. Initial
source CI exposed a stale Core-only coordinate expectation after the approved SDK
recipe addition; `40a3531` updated only that expected dependency tuple/companion,
retaining exact whole-file and unchanged-product assertions.

Ordinary pinned CI35456792284/job105933403088 at `40a3531` passed 26 support and
443 package tests, including gateway 56/all seven new laws. Existing numeric,
source/published baseline, root launcher/denial and cleanup stages completed;
final residue audit passed. [Evidence and log digest](https://github.com/OpenJ92/control-plane-kit-servers/pull/218#issuecomment-5743768008).
Source review and final-head acceptance are recorded on the PR.

Coverage: `cpk-local-gateway` counts once as one family/one catalogue identity.
Relay and own-health are two responsibilities of that product. This entry records
source coverage; historical images do not acquire the new capabilities.

Handoff: #148 still owns concrete local observation transport, #188 connector
truth, and #181/#1860 production provenance/current authority and lifecycle/history.
Production composition must supply the exact third artifact and teach its
receiver-trust selection about the gateway's workload-health role; parsing alone
is not current authority. Minimal public status is not a protected correlated
observation or authenticated management-path proof. Source recipe and package
tests do not establish image qualification, live TLS/DNS or cluster acceptance.
Root mutation permission/external behavior remain unverified in the ordinary gate.

No durable mutation, provider action, new exposure, retry policy or additional
socket recipient is introduced. The existing relay is preserved. Parent-required
legacy route/wiring/doc retirement remains separate and incomplete; removing two
obsolete source verification entries does not close that broader obligation.
