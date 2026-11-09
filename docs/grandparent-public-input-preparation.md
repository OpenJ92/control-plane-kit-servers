# Public document preparation without commissioning fixtures

The accepted six-role image input is already recorded separately. Preparing its
gateway product document must not invoke the full assembly fixture, whose setup
creates synthetic receiving and signing material. The new metadata-only owning
entry is `./test.sh --prepare-grandparent-public-inputs CORE_REPOSITORY MODE`.
It exits through the existing cached preflight helper before policy/build,
registration exports, network allocation or PostgreSQL. MODE is `gateway` or
`website`; both use exact Coref56bb5c4, the selected immutable cached validator,
network none, read-only mounts and this checkout's real source. No host Python,
ad hoc Docker harness, image build/pull or registration is involved.

`gateway_document(images)` uses the existing canonical catalogue document,
selected gateway image and the existing HTTP-sample declared runtime contract.
The output is the Core canonical ProductDescriptorDocument bytes without an
extra newline. Its declared configuration slots are retained; it contains no
commissioned receiver or private material. A prepared regression requires exact
equality with the full assembly's gateway document and forbids fixture/material
setup in this independent path.

`parent_website_input(images, public_input, receiver_id=...)` decodes the approved
parent commissioning public.json, checks its exact byte hash and target scope,
and uses only its two purpose-specific public verifiers. It requires distinct
canonical HTTPS API/site origins and an explicit loopback visitor binding. The
existing website product factory encodes a fresh website receiver at the parent
website node/control socket. Reusing a parent receiver or foreign workspace is
refused. CLI mode allocates one new PUBLIC UUID receiver identity; it generates
no private key, bearer or secret. The output is the normal root `website` input
stanza, with the explicit managed configuration artifact. The root's existing
API endpoint remains the upstream source of truth.

The source tests for these helpers are prepared, UNEXECUTED. Previous63645d0
green evidence predates them. Exact source/action review and release must precede
either metadata command; this note is not a test receipt or action approval.
Both commands require a fresh, exclusive output path and preserved stderr/status.
Website preparation must run only once after review: a repeated command would
allocate another public receiver. Failure stops for owner review, without retry.

Action shape, from this checkout (public environment values are loaded from
the exact reviewed files, with normal shell file reads):

```sh
DOCKER_CONTEXT=desktop-linux
CPK_SOURCE_IMAGE_VALIDATOR=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
CPK_SOURCE_ASSEMBLY_IMAGES=$(cat /private/tmp/rowan-163-six-role-images.json)
CPK_SOURCE_PARENT_WEBSITE=$(cat /private/tmp/rowan-384-parent-website-public-preparation.json)
export DOCKER_CONTEXT CPK_SOURCE_IMAGE_VALIDATOR CPK_SOURCE_ASSEMBLY_IMAGES CPK_SOURCE_PARENT_WEBSITE
./test.sh --prepare-grandparent-public-inputs /Users/jacobvartuli/.codex/worktrees/23a6/control-plane-kit gateway
# Website is a separate reviewed invocation of the same entry with mode website.
```

Decision: reuse existing Core codecs, gateway declared contract, website
configuration factory and cached owning preflight. Rejected the assembly fixture
as an authoring tool for actual inputs; rejected synthetic keys/receiver IDs and
parent identity reuse for the child. Child PostgreSQL still needs its actual
child public receiver plus the selected original SQL/password reference in the
normal installation variant; this helper does not fabricate that document or a
complete sender artifact.

Security/data/history: only approved public files are inputs, no private path is
opened, no runtime/provider/store mutation occurs and no listener is started.
No new route, grant or network exposure is introduced. Public output allocation
and hashes must be recorded; cleanup removes only the helper's public source
scratch. Actual protected preparation, installer qualification, registration,
DNS and startup remain with their existing owners and reviewed effect boundaries.
