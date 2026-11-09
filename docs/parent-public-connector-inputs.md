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
green validation remains unexecuted. An unvalidated checkpoint precedes the
released green gate; unexpected execution failure stops without retry.
Actual rendering is a separate reviewed invocation of the existing public-input
command with mode connectors, fresh exclusive bundle/output paths and preserved
status/stderr. No one-shot external launcher is introduced.

Security: public read trust only, no new grant, route, network exposure or live
mutation. These are receiving files for connector management port8000; visitor
traffic uses each tunnel's separate Cloudflare ingress configuration and token.
Port8000 is never published. Files alone prove no connector/tunnel/TLS/login
readiness. Private token custody and later bootstrap/external effects stay with
their approved owners. No real plan or activity history is fabricated.
