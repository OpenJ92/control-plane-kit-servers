Source: [products/cpk_server/tests/test_image_bootstrap.py](../../../../../products/cpk_server/tests/test_image_bootstrap.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This broad unittest file covers CPK packaging, bootstrap parsing/composition,
provider import boundaries and smoke-harness structure. Its coordinates come
from server-products.json, so imported contracts must be checked at that
consumer's selected Core/Operations and Interpreters revisions. It combines
real local parser/value/dispatcher calls, patched collaborators, AST inspection,
plain source-string assertions and selected shell early-rejection subprocesses.
The file's name is not evidence that every test launches the image.

Bootstrap tests require all four store selectors, closed runtime/material/signer
choices and explicit authentication configuration. The legacy configured flag
alone does not construct a credential verifier. Legacy Docker credential
bootstrap is rejected; Ed25519 signing and Cloudflare ingress require provider
material. Local-development material has its own explicit parser/resolver cases.
Selected repr checks protect credentials/material and process projections; they
do not certify every configuration field or output as secret-free.

The gateway dispatch case composes the actual dispatcher with a generated test
Ed25519 key, an injected authorized resolver, fake public DNS and MockTransport.
It checks grant forwarding, signed claims and bounded success/failure evidence,
including rejection of a loopback public address and denied key resolution.
This exercises local composition and signing without an actual secrets provider,
public gateway, network TLS handshake or durable authorization transaction.

Dockerfile/bootstrap-descriptor assertions protect publication inputs and
declared process boundaries. AST/source checks constrain concrete provider
imports, lazy construction, raw ASGI query forwarding and readiness fields.
They are structural contracts, not executed provider-lifecycle or readiness
proof. Harness sections check expected calls, scopes, selected graph shapes,
verification policies, image coordinates, restart/history/cleanup ingredients
and fixture ordering. The convergence launcher includes actual early argument
rejection checks; those do not execute its deployment path.

When using these tests as navigation, inspect the owning launcher/controller
before inferring a runtime guarantee. Existing legacy hosted/recursive settings
conflict with current bootstrap, some graph fixtures remove health checks, and
Cloudflare abort ordering does not establish retention after failed cleanup.
Source-text assertions can remain satisfied despite those defects. No new
upstream permissions element should be imposed merely because another Core
revision introduced it; compare the selected codec and target contract first.

Review here inspected the full test-name inventory and selected behavioral and
harness sections, not every permutation in this large file. Read with
[server composition](../src/control_plane_kit_servers_cpk_server/server.py.md),
[image smoke](../../../scripts/cpk_server_image_smoke.sh.md),
[hosted workflow](../../../scripts/cpk_server_hosted_activity.py.md),
[recursive launcher](../../../scripts/cpk_server_recursive_activity_smoke.sh.md)
and [Cloudflare launcher](../../../scripts/cpk_server_cloudflare_secret_custody_source_live_smoke.sh.md).
Executable validation belongs to the repository's Docker-backed suite.
