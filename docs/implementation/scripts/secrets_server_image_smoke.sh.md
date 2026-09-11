Source: [scripts/secrets_server_image_smoke.sh](../../../scripts/secrets_server_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This standalone Docker smoke builds the Secrets product/controller by default,
or requires a digest-shaped product reference when product building is disabled.
It creates a run-labelled network and three volumes for provider bootstrap,
client bootstrap and retained provider data. A root helper generates synthetic
key/token/application material inside those mounts and assigns the provider
files and data to UID 10006. The provider uses private network HTTP without a
published host port; this script does not establish TLS or a public CPK path.

A controller uses the selected public Secrets client to write an application
secret, generate and replay a gateway signing key, verify the derived public
key, revoke that exact version and require revoked resolution to fail. The
provider container is then forcibly removed and recreated against the same
data/bootstrap volumes. Resolving the application value afterward is this
script's retained-data witness; it does not test an entire parent/child
installation or preserve the fixture after completion.

Readiness bounds individual HTTP attempts and their count, but Docker commands
and full log reads have no explicit overall deadline here. Log checks search
selected forbidden markers and exact token/application values; matching grep
output can itself print sensitive lines on failure. The temporary cat helpers
used for those checks are --rm containers without the run label, so the
label-based cleanup inventory does not cover them.

EXIT/interrupt handling retains the original status, attempts labelled
container/volume/network cleanup and checks for remaining labelled resources.
Cleanup command failures are suppressed, and the final shell pipelines do not
make a Docker listing failure a reliable absence verdict. Images are retained.
These limitations belong to this historical harness; its existence is not
authorization to execute, delete resources or retry an ambiguous operation.
Product tests inspect its wiring; an actual smoke result is separate evidence.

Related source and evidence: [products/secrets_server/Dockerfile](../../../products/secrets_server/Dockerfile), [products/secrets_server/product.cpk.json](../../../products/secrets_server/product.cpk.json), [products/secrets_server/bootstrap.contract.json](../../../products/secrets_server/bootstrap.contract.json), [products/secrets_server/tests/test_secrets_server_product.py](../../../products/secrets_server/tests/test_secrets_server_product.py), [test.sh](../../../test.sh), [coordinates/server-products.json](../../../coordinates/server-products.json).
