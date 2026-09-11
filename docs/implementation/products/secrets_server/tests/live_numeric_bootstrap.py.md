Source: [products/secrets_server/tests/live_numeric_bootstrap.py](../../../../../products/secrets_server/tests/live_numeric_bootstrap.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This executable fixture witnesses the actual source images' numeric-user and
protected-file boundary through the selected Docker SDK and public Secrets
client. Its caller supplies engine, image, helper and network coordinates. It
checks the engine ID, network labels and image run label before creating its
fixture resources; those comparisons do not independently authorize a run.

The CPK helper first exercises a UID 10001 recipient. This owner then
materializes both Secrets bootstrap files into distinct named volumes, checks
UID 10006, 0400 mode, regular-file evidence and content digests, and starts the
actual provider with a separate data volume. Runtime probes check account/HOME,
process UID, mount identity and read-only access; a UID 10007 container must
fail to read the files. A synthetic authorized client writes/resolves one
application value, and an invalid credential must be denied.

Readiness uses bounded HTTP attempts. Selected exec output and log tails are
checked against the fixture's sensitive values; provider logging has a size
rotation setting. This is selected redaction evidence, not a universal log or
exception sanitizer. The fixture supplies generated local credentials, not a
parent's custody admission or the held child-deployment acceptance path.

The finally block removes recorded resources in reverse order after checking
the run label, then requires lookup absence for those identities and recorded
configuration helpers. The surrounding gate owns the network and built images.
Resource/helper identities are recorded after creation returns, so an ambiguous
create before recording is not covered by this list. Cleanup failure raises
instead of printing the final passed JSON; this is not a prospective recovery
journal, blind-retry instruction or restart-history test.

Related source and evidence: [products/cpk_server/tests/live_numeric_bootstrap.py](../../../../../products/cpk_server/tests/live_numeric_bootstrap.py), [products/secrets_server/Dockerfile](../../../../../products/secrets_server/Dockerfile), [products/secrets_server/bootstrap.contract.json](../../../../../products/secrets_server/bootstrap.contract.json), [scripts/secrets_server_image_smoke.sh](../../../../../scripts/secrets_server_image_smoke.sh), [test.sh](../../../../../test.sh), [coordinates/server-products.json](../../../../../coordinates/server-products.json).
