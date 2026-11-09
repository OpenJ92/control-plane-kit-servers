# Child PostgreSQL public variant and sender handoff

Governing work: #163 child deployment, #384 isolated sender. This source slice
follows cdb872a public gateway/parent website preparation; it leaves that reviewed
checkout fixed and uses separate codex/163-child-public-postgres. Rowan owns the
narrow installation.py extraction; Vale owns protected material preparation;
Linnaeus owns installer/runtime packaging. No live action belongs to this slice.

The actual child public commissioning record exists at the North-approved
public.json path, SHA25637fc01359f6cce40df1ae237f198d6af9760a08fa504c63d06cec01ac6395db2.
The child namespace is cpk163-child-20261109. Its CPK/Secrets receiver IDs are
distinct from the parent's. These are public input facts, not private PEM inputs.

## Source trace and chosen shape

Previously installation._postgres_variant consumed a whole DockerCpkInstallation,
although PostgreSQL construction used only its postgres_product/postgres_password.
Its managed branch adds the original installation-postgres-ready SQL check,
binds that SAME SecretReference into POSTGRES_PASSWORD_FILE delivery, then calls
the existing _variant owner for the product identity and canonical contract hash.
The missing connection was public preparation of that exact value without an
unrelated full installation, test fixture or private material generator.

installation_postgres_product(document,password_reference) now owns that unchanged
construction. _postgres_variant delegates to it. Direct callers additionally
pass normal selected-product and typed-reference validation. No SQL law or
identity algorithm is reimplemented by the renderer.

child_postgres_document validates the exact commissioning public bytes/hash,
two verifier purposes and child workspace/runtime/CPK scope; allocates only one
fresh public receiver at child-postgres/management using the existing PostgreSQL
configuration factory; selects the accepted wrapped PostgreSQL image; and calls
installation_postgres_product. The proposal's public logical password reference
is secret://control-plane-kit/cpk163-child-20261109/postgres/password. Nothing
creates or resolves that secret/version. The resulting once-prepared canonical
document must be used verbatim by BOTH sender configuration and later import.

sender_input decodes the exact prepared gateway/PG documents with Core's normal
codecs and emits the EXISTING cpk-server.managed-verification.v1 startup schema:
gateway ProductReference plus the exact PG canonical document string. It does
not replace the ordinary startup reader's support/observer checks. Sender mode
allocates no ID. PostgreSQL mode allocates one public UUID, never a signing key.
Sender preparation additionally requires independent frozen SHA256 values for
both ordered inputs. It refuses swapped roles and any otherwise valid alternate
document before emitting output. Use the previously accepted gateway hash and
the exact PG hash captured after its single preparation; do not recalculate an
expected hash from an unreviewed replacement during sender generation.

Rejected: using AuthoredMaterial/managed_input fixtures for actual documents,
borrowing parent receivers or trust, constructing a fake installation object,
copying the SQL/variant algorithm into a script, or selecting stock gateway-smoke
PostgreSQL instead of the qualified wrapped image.

## Test context and action

New-law equality: independent public preparation equals the normal complete
assembly's canonical PostgreSQL variant and product reference for the SAME
product, receiver and password reference. Assertions preserve original SQL check,
file delivery, shared password binding, image and content-derived identity.
Changing the password ref changes the variant; crossed scope/hash/reused receiver
refuse. Helper invocation forbids fixture/private material setup. Exact sender
PG bytes and gateway reference are asserted. Public parent/gateway and previous
full/legacy image-input laws are included to protect shared decoding changes.

Maintained tests select five pure ManagedPostgresInstallationTests laws: original
SQL/file-control projection, scope with/without website, verifier/receiver refusal,
wrong file/contract rejection, and native historical behavior. No process/DB is
started. Existing owning policy/support/integrity and cached source export cleanup
remain. All source tests are PREPARED, UNEXECUTED at this checkpoint.

After exact independent review/release, the source-only owning action is:

```sh
DOCKER_CONTEXT=desktop-linux \
CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba \
./test.sh --child-public-postgres-source-tests \
  /Users/jacobvartuli/.codex/worktrees/23a6/control-plane-kit \
  /private/tmp/cpk1815-http-sender /private/tmp/cpk2089-native-postgres-readiness
```

The selector fixes Coref56/Ops701/Ie438, actual checkout source paths before /app,
immutable cached controller, network none/read-only/tmpfs/no socket, then exits
before build or registration. No host Python or alternate test harness.

After source PASS and separate action review/release, existing metadata entry
`./test.sh --prepare-grandparent-public-inputs CORE_REPOSITORY postgres` takes
CPK_SOURCE_ASSEMBLY_IMAGES and CPK_SOURCE_CHILD_POSTGRES (the reviewed public
preparation JSON) and writes one canonical PG document to a fresh exclusive file.
Mode sender then takes CPK_SOURCE_GATEWAY_DOCUMENT/CPK_SOURCE_POSTGRES_DOCUMENT
with those exact bytes and emits the existing sender JSON to another exclusive
file. Sender also requires CPK_SOURCE_GATEWAY_DOCUMENT_SHA256 and
CPK_SOURCE_POSTGRES_DOCUMENT_SHA256 frozen as described above. Preserve
status/stderr/output hashes and stop on any failure; no retries.
Do not rerun gateway or parent website allocation during these steps.

Security/history: no new route, grant, network exposure or durable mutation.
Only public verification material and logical SecretReference metadata are
decoded; no private PEM, bearer, selected secret version, run or receipt is read
or invented. Public IDs and output hashes are recorded on the governing issue
through North. Real installer qualification, protected preparation, graph
submission, runtime startup and ingress remain separately bounded.

Meridian's first review held two details before any test or PG allocation:
the extraction's exact-type reference check narrowed the existing isinstance
contract, and sender input roles were not independently bound to accepted bytes.
The successor preserves isinstance with a focused reference-subtype regression,
and requires the ordered frozen hashes with swapped/alternate-document refusal.
No test, metadata retry or receiver allocation preceded this correction.
