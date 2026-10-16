# Selected secret composition — #252

Current checkpoint implements the typed metadata bridge and shared-factory port;
runtime witness extensions and complete installed-dependency validation remain
pending. It does not claim final #252 or grandparent acceptance.

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

No new provider-live, image-publication, credential, original tunnel/DNS/token or
shared-resource cleanup authority follows from this composition. Current provider
observations do not establish installed material. Runtime verification and exact
owned cleanup must supply their own maintained witness evidence.
