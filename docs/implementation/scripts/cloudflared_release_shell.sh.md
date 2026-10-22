# Managed release owner entries

The owning test.sh routes controller acquisition and focused release tests before broad setup. Acquisition builds only Dockerfile.test from clean source and retains source/tree/recipe/image/build receipts. Focused tests require an exact cached controller plus explicit receipt, mount current source read-only, receive no daemon socket, and cannot pull/build implicitly. They retain failure evidence and prove release behavior only, never managed OCI/live acceptance.
