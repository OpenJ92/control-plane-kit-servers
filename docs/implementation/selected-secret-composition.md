# Selected secret composition — #252

Current checkpoint implements the typed metadata bridge, shared-factory port,
and maintained witness extensions. Post-adoption execution and complete
installed-dependency validation remain pending. It does not claim final #252 or
grandparent acceptance. Kepler passed the bounded bridge/adoption source at
`c3740e7dfc13f1a87d44af12e71617341e175520`; witness review remains pending.

The accepted dependency tuple is deliberately package-specific: Core
`87e231c661879e44816ba71ff9320c040c868d60`, Operations
`2bd0211798c55addab1fd3135ee72371791ff566`, Interpreters
`0ef3c98f16382a56e4858aa822168978481b34de`, SDK
`ad0582937d7e41f1e7a41295fa1de58c2ce4cba2`, Secrets
`b3e6d21f1f53c3ad2fe9ec33900ddde0611e2b5a`. Core's complete subtree at both
CPK commits is `a724448b4a63e3c3ba345333df2351cf0b247b5e`; #1989 changed only
Operations. The existing Core URL matches all accepted external direct pins,
while Operations' version requirement admits it. North and Kepler independently
confirmed this split; no resolver override or pin relaxation is used.

Tests-only checkpoint `a4f5af4` ran through unchanged `./test.sh` on old pins.
Support26/root48/Cloudflare19/gateway59 passed. Cpk-server389 methods produced
8 assertion failures across the three changed metadata/factory methods, solely
for missing composition. Negative subcases stopped at the missing bridge and do
not independently establish each metadata refusal law as red. No import/setup
errors or later runtime witness execution occurred. Log SHA256:
`d2e107b5df965b52bf5612fa42a20937762bbb6c74ecac3115e06ea1d4b5c301`.

The public witness uses authenticated `desired-graph.set` for explicit choices,
then existing plan/approve/execute surfaces. TopologyClient.plan authors another
revision through deployment.prepare; the witness must prove exact carry-forward
into its approved graph rather than call that operation a pure read. Initial
pending draft/revision receiver provenance and original retry coordinates remain
unchanged. A demonstrated inability to preserve those laws is a stop, not license
for private authoring, a new frontend API or another workflow/state machine.

The unchanged pending baseline deploys first. The witness then imports two
fixture product variants, publicly admits one application reference/provider,
and explicitly selects an environment-delivered version for the existing api
node. A second selection changes only the version. A final product edit changes
the image and one independent application configuration artifact while retaining
the exact selected version and receiver configuration. Genuine runtime receipts,
actual container identity/old absence, public committed events, original action
replay and client history are asserted; named-user Hello is not file-delivery
coverage. The numeric-file fixture separately checks full selected volume identity,
UID/version separation, first allocation label retention and fail-closed cleanup.

Bounded effects: the existing isolated provider writes exactly three application
versions and revokes the third during setup, separately from consumer execution.
Missing/revoked choices must refuse before dispatch and without desired-pointer
changes. Existing Docker scope remains four nodes and one owned runtime network;
three api replacements extend the retained configuration-volume record. Every
allocation is recorded before dispatch, with the existing record-size bound.
Cleanup retains the owning gate's exact IDs, independent ownership checks,
detachment checks and non-force volume deletion. No broad discovery-driven
deletion is added. Provider plaintext is private and no secret digest is emitted.

The first post-adoption gate at `73689a1` installed the complete accepted tuple
and passed 26 support checks, then stopped at root48/F1 before product/runtime
tests. The retained application script changed deliveries without rebuilding
Core's now-required total selection values. Both that script and the new consumer
fixture now call canonical `author_secret_selections` in the same replacement:
new uses remain explicitly unselected and compatible choices carry forward. North
released this narrow adoption; Kepler confirmed it does not establish an owner
gap. The old script's fake-route convergence test is orchestration-only; this
change does not add fresh explicit-version preparation to its live workflow.

Kepler identified an evidence weakness in catch-all client error assertions.
The negative fixture now observes the actual forwarded metadata bridge refusal
for exact requested coordinates, and verifies both completed effects and the
pre-dispatch intent count remain unchanged. Original action replay requires no
new metadata observation. Public graph descriptors are redacted projections:
the fixture retains its original declared choice after checking fresh public
coordinates, while the actual later request/receipt proves admission and carry-
forward. No private graph read or reconstructed historical state is used.

No new provider-live, image-publication, credential, original tunnel/DNS/token or
shared-resource cleanup authority follows from this composition. Current provider
observations do not establish installed material. Runtime verification and exact
owned cleanup must supply their own maintained witness evidence.
