# Fresh local sibling preparation (#399)

North coordinates, Linnaeus prepares, Meridian reviews. Repository Servers,
branch `codex/399-grandparent-mcp-packet`, destination
`roadmap/1813-runtime-control`. This is operator bootstrap, not a CPK deployment
or completion of #399's installed Codex acceptance.

Jacob has released preparation after Meridian reviews these actual inputs:
check the five cached images and fresh names/ports, generate fresh private
material and compile/verify the public plan. Return that result to North before
starting services. Feasibility PASS alone does not release preparation.

The sibling is `cpk399-sibling-20261114-01`. API/MCP use loopback18263;
website uses loopback18264. No old resource, identity, credential, graph or
route is selected. Stop on a collision or missing image. Do not pull, rebuild,
change ports, retry an ambiguous action or clean up another installation.

## Public inputs and source recipe

`sibling399/commissioning-intent.json` is the complete fresh public commissioning
intent. `sibling399/material-template.json` freezes principals, scoped grants,
references, custody and the official PostgreSQL descriptor. Its CPK/Secrets
products are intentionally null until new commissioning output exists. It is
not an executable material input. No old trust or managed-health/verification
configuration is copied. This first workspace-read boundary has no management
grant/capability or child/external provider policy.

`scripts/grandparent_sibling_prepare.py` performs public-only transformations:

1. `commission-intent` and `material-template POSTGRES_DESCRIPTOR` reproduce the
   staged inputs.
2. `bind-material TEMPLATE COMMISSION_PLAN PUBLIC COMPLETE` builds CPK/Secrets
   products through the installed0d5 public contract factories. It explicitly
   selects49ae and `CPK_MCP_PROFILE=grandparent-read-only-v1`, then validates with
   the actual installed material owner. It prints the unprojected CLI input;
   no private generation or provider call occurs.
3. `website-artifact PUBLIC FRESH_RECEIVER_ID` decodes only new public CPK trust
   with Core and replaces the target/declaration using the existing website
   product factory. Receiver ID is allocated only after release. It emits a
   public artifact descriptor; its content becomes the fresh0444 public file.
4. `website-action BOOTSTRAP_PLAN APPLY_RESULT WEBSITE_ARTIFACT` freezes native
   create/start argument arrays using the completed new receipt's exact network
   and CPK IDs. It never invokes Docker. There is no stop/rename/remove action.

Use the pinned installer0d5 and recovered source3d `bootstrap.sh` entry
SHA256877809d31064eb948cd137f64b1a06a8c61b0080eb1ce42f2d1c2e8c8f277f31.
Invoke its normal commission-plan/commission-prepare and material-plan/
material-prepare commands; do not substitute this checkout's older launcher.
`material-plan` receives the new public SHA256 and commissioning intent digest
and attaches the public snapshot itself. Do not put commissioning in its input.
Material parent and leaf must both initially be absent; read-trust custody is
separate. UID/GID501:20 is proposed and must match actual custody before use.

Public rendering runs in a socket-free, network-none, read-only installer helper
with the reviewed repository mounted `/source` read-only and only individual
new public files mounted. The website factory is loaded from the repository's
existing `products/website_server/src`; installed CPK/Secrets owners stay selected.
Real signing files, private policy, bearer files, index and whole material or
commissioning directories are never mounted to this renderer. Keep final public
output hashes and validate the compiled exact resources/grants/profile before
apply. Resource ceiling is three backend services, two data volumes and no more
than ten total root volumes; final exact list depends on fresh artifacts.

## Website create-only step (later release)

The returned native arguments select image93627, its default node-managed
wrapper, new receipt network, sibling alias, `CPK_WEB_UPSTREAM` equal to
`http://cpk399-sibling-20261114-01-cpk:8080`, and only127.0.0.1:18264->8080.
The only host bind is the fresh public0444 control file, readonly at
`/etc/cpk/website/control.json`. Root filesystem readonly, no capabilities,
no-new-privileges, `/tmp` tmpfs, no logs, restart=no. No Docker socket or
private material goes to the website. Management8000 remains unpublished.

Persist the exact reviewed action and pending create before submitting once.
Record and validate the returned CID/cidfile before recording pending start
and submitting one start by that CID. Preserve partial evidence on interruption;
do not redispatch. The supplemental receipt owns this initial website; do not
fabricate CPK graph/history truth. This is on the same Docker daemon, not a
daemon security boundary. Native inspection must confirm the new network/CPK
alias and actual website image/proxy/bind/ports before a human bearer is used.

## First acceptance and exact client (later release)

Only fresh-human browser login/workspace overview and SDK MCP discovery plus
one `get_workspace` are in the first check. Both must return the new workspace
ID. No draft save/select, other MCP tool call, graph comparison or setup
credential in either client. The schema's `.invalid` HTTPS origin is an unbound
declaration; actual acceptance uses HTTP loopback. No DNS/TLS/public route is
created or claimed.

`scripts/grandparent_sibling_mcp.py` uses the qualified49ae image's
`mcp.Client`2.3.0 + `httpx2.AsyncClient` + `streamable_http_client`, mode=auto.
Exact recipient: `http://127.0.0.1:18263/mcp`. Private delivery reference:
`/Users/jacobvartuli/Software/self/control-plane-kit-servers/env/cpk399-sibling-20261114-01-prepared/material/human.bearer`
as an individual readonly bind at `/credentials/human.bearer`. Run as501:20;
require0400/64bytes and existing ClientProfile's private-file admission.
Metadata/access failure stops; do not chmod, remap UID, copy a setup bearer or
relax the loader. No value in argv/env/output/URL/report. Reports contain only
client/version, discovery names, endpoint and returned workspace ID.

Freeze a single named helper, qualified49ae image, default image imports,
`--network host`, user501:20, readonly/cap-dropALL/no-new-privileges, no socket,
no logs, bounded tmpfs and only this script plus the one human file as binds.
Docker Desktop host networking is an explicit prerequisite to check without a
credential; stop if unavailable rather than silently changing recipient.
Proxy variables are empty and `trust_env=False`, redirects disabled; the whole
operation is bounded45s. No native Codex client configuration is changed.
SDK success is server-path evidence, not attachment of this Codex chat.

Browser credentials are privately entered for the fresh human. Record the
observed browser workspace and actual client; historical Nov12 browser success
is supporting evidence only. No secret in screenshots or durable records.

## Owning validation

`DOCKER_CONTEXT=desktop-linux ./test.sh --grandparent-artifact-source-tests`
runs syntax/support/integrity, existing finite source cases, actual frozen
installer contracts and the new synthetic public composition tests. No live
input, Docker socket in helpers, provider/network, key generation or service
start is used. The sibling tests compile the actual owner plan, render through
the website/Core factory and bind native args to synthetic new receipt IDs.
They are source/composition evidence, not fresh runtime or SDK connectivity.

Stop on apparatus failure. Publish the checkpoint candidly as unvalidated before
this gate, and record terminal evidence and Meridian input review on #399.
