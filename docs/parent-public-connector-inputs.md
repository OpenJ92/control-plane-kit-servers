# Parent public connector preparation

Governing artifact: Servers #384. Base be40a0d extends the already exercised
metadata-only public input command. The product owner remains
cloudflared_connector.managed.control_configuration_artifact; this adapter owns
only selecting two distinct public receiver targets and passing the exact parent
commissioning trust into that renderer. It allocates no credentials or keys.

Target public interface: parent_connector_inputs(images, public_input,
receiver_ids={api: ..., website: ...}). Inputs are the same six-image mapping,
exact commissioning public JSON and its SHA256, workspace/installation IDs.
Targets are <installation>-external-api-01 and -external-website-01, socket
control, in the parent's existing Docker runtime. Each output is the product's
0444 /etc/cpk/cloudflared/control.json artifact. CLI mode connectors allocates
two public UUID receiver IDs once and returns a bundle containing both artifacts.
Host extraction preserves the exact artifact content bytes.

New-law tests require exact equality with the existing product renderer and
parent verifiers, distinct receiver IDs, refusal of parent reuse, crossed scope,
bad hash, malformed ID and unknown roles/fields. Source dry run: image_options
validates all six public images, _commissioned_configuration validates frozen
public bytes/parent scope and two read-only purposes, then the connector factory
validates its own declaration. No fixture, provider, network or private material
owner is entered by actual rendering. Tests alone use isolated synthetic fixtures.

Owning source gate: ./test.sh --parent-public-connector-source-tests CORE OPS
INTERPRETERS, using the existing immutable cached controller and exact
Coref56/Ops701/Ie438 exports. Target-red at a5fc14a passed28 support and ran both
focused tests (2.429s), producing nine identical missing-adapter errors across
the positive and negative subcases. Source setup/imports succeeded. Meridian
independently passed this intended red. Implementation is now prepared;
green validation and the one public render passed as recorded below. An
unvalidated checkpoint preceded the released green gate; unexpected execution
failure stops without retry.
Actual rendering is a separate reviewed invocation of the existing public-input
command with mode connectors, fresh exclusive bundle/output paths and preserved
status/stderr. No one-shot external launcher is introduced.

Security: public read trust only, no new grant, route, network exposure or live
mutation. These are receiving files for connector management port8000; visitor
traffic uses each tunnel's separate Cloudflare ingress configuration and token.
Port8000 is never published. Files alone prove no connector/tunnel/TLS/login
readiness. Private token custody and later bootstrap/external effects stay with
their approved owners. No real plan or activity history is fabricated.

## Terminal source and public output

Reviewed implementation4812d748 passed28 support and both unchanged target tests
(2.494s), including owned source scratch cleanup. The complete source log SHA256
is 5b959f4c66b70618f7b6c1b87f7013d4ba5dc78187e1199d5b08d148e01c8cbb.
Meridian independently confirmed the intended red and green. North separately
released the single offline metadata render after green; it exited0 with empty
stderr. No source, build, provider or rendering retry occurred.

The3432-byte public bundle SHA256 is
88686a3fd3fa12ae624e906e79d149539d2a57f1318a63e9465cab9ae83c303f.
Exact raw API control bytes SHA256
81848cf014133a3d96710c457725aa076efe849719c7074fefd33da6fa228ee1,
receiver8805de570d1d4611b25791435ba0e114. Exact raw website control bytes SHA256
469db25cd1bb75d4517fa827f11956ca8915b023530c5897f20efc2f03956c20,
receiverff208cf2d899486f8afbfa32b66b8fc3. Both raw files are0444 and match
their product artifact content_digest. North has the exact local file locators
for Vale integration and final independent review; no credential locator was
included.

The two new IDs are distinct from each other and all three previously issued
parent CPK/Secrets/website IDs. Both exact verifier arrays match the approved
parent commissioning public bytes, and the workspace/runtime/node/socket
targets match the proposed two external connectors. The unchanged selected
connector image is812262a6, and the six-child image file remains byte-identical.

Integration uses CPK_WRAPPER_CONFIGURATION_FILE pointing at each mounted
read-only /etc/cpk/cloudflared/control.json. TUNNEL_TOKEN_FILE is a separate
protected delivery. Do not publish8000. The approved external operator must
still verify its actual network/service/route/token and bootstrap receipt joins;
these source/public-file results prove no ingress, TLS, login or live health.
