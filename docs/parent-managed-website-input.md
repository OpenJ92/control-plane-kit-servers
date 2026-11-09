# Explicit managed website in an external parent bootstrap

The sibling grandparent website uses the accepted managed website image, whose
default entrypoint requires its own public control artifact. The former root
website input dropped that artifact and selected the ordinary frontend contract.
This source change preserves the explicit artifact through normal root planning.

Existing `installation.website` retains required `image`, `external_endpoint`,
`host_binding`, and accepts optional `managed_control_configuration`: the normal
Core ConfigurationArtifact descriptor from the website product factory. It is
public receiving material, not customer auth or an arbitrary file path to read.

For the parent with external API and website origins, the existing installation
composer admits that explicit managed contract without requiring the CHILD's
gateway/three-ingress group. Named managed-child behavior and ordinary external
website behavior stay on their existing paths. The normal website factory still
requires distinct HTTPS API/site origins, fixed visitor8080, authenticated
management8000 and the exact product control slot/declaration.

Review corrected the old management-required negative to a NAMED-ingress input
without its management group; its original invalid-artifact/nonreflection
assertions remain. The new external-parent positive is a deliberate separate
admission case. The focused action must include all CompleteRootPlanTests and
existing managed-website cases, not just the two new tests.

Target scope must match the parent installation workspace/runtime/website node
and control socket. Root receiving validation additionally refuses a website
receiver ID reused from its CPK, Secrets or managed PostgreSQL receiver. A child
scope cannot stand in for the parent's receiver. Actual parent website receiver
allocation belongs to approved parent public preparation, inheriting only its
approved purpose-specific public verifiers; private keys are not read/generated
by this source change.

Two new normal `CompleteRootPlanTests` cases cover a distinct parent namespace,
exact public artifact/content digest, exact visitor/API origins, root plan
configuration-file projection and wrapper environment. Host bindings publish
only visitor8080 on loopback; no management8000 binding is added. Negative cases
reject child workspace/runtime/node and reused parent receiver IDs. Existing
ordinary external website, invalid origin/binding and managed-child laws remain.
These focused tests are prepared but UNEXECUTED. No service/DNS/credential work
or packaging edit has occurred; source review and owning cached test selection
remain pending.

Reviewed-source action candidate (not yet run):

```sh
DOCKER_CONTEXT=desktop-linux \
CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba \
./test.sh --parent-managed-website-source-tests \
  /Users/jacobvartuli/.codex/worktrees/23a6/control-plane-kit \
  /private/tmp/cpk1815-http-sender /private/tmp/cpk148-native-http-sample \
  f56bb5c4cfde76764d39c5377d4270c5b23c3ba1 \
  70154b6698e101159326b08646f2dba90dda87cd \
  e438f6e522ad0a23a7acef460be08690f48b2e17
```

The existing cached startup mechanism runs normal support/policy/integrity,
then all CompleteRootPlanTests and four maintained managed-website laws. Exact
source/dependency overlays and every required product source/test path precede
cached /app; controller is immutable, no pull/build, network none, read-only root
with temporary synthetic test files. No real key/protected input, database,
Docker socket, service, registry or DNS action is used. Actual installer/driver
qualification remains separate from the listening runtime image.

Decision: reuse existing public artifact codec and frontend product constructors
instead of adding another website wrapper or accepting extra environment flags.
The new shape is one optional public value -> existing installation composition
-> the ordinary inspectable bootstrap plan. Normal bootstrap runtime already
mounts those exact configuration_files read-only. No alternate launcher is added.

Security/history: no new route or permission, no secret values/customer bearer in
the artifact, no wider network exposure, and no runtime/retained-data mutation.
Public plan generation is not service startup or successful customer auth.
Actual protected preparation, image launch, two public origins/DNS/tunnels and
known-workspace login/read proof keep their separate reviewed effect boundary.

Vale retains offline material preparation and its CLI; Rowan's bootstrap.py
ownership is restricted to this optional website stanza and receiving-identity
check. Linnaeus owns packaging/gate integration. Governing parent work is #384
with the child/source boundary coordinated under #163.
