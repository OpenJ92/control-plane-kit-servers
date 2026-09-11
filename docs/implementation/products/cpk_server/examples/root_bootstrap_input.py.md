Source: [products/cpk_server/examples/root_bootstrap_input.py](../../../../../products/cpk_server/examples/root_bootstrap_input.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This example reads the checkout's CPK Docker/Cloudflare, Postgres and Secrets
descriptor JSON and returns or prints a portable root-bootstrap input. It
defaults to a /source mount, placeholder installation/workspace IDs, loopback
host binding and an example external endpoint. File read/JSON errors propagate;
the helper does not admit descriptors or validate the resulting plan.

The output names a local-Docker-socket delivery kind, opaque authority and
secret references, an explicit list of workspace scopes and setup provider
intents. Those are proposed input values, not acquired credentials, granted
authority or verified resources. Editing IDs, products, references or scopes
requires review by the real bootstrap parser/plan. Printing it creates no
credential, plan, registration or deployment.

The live root fixture consumes this helper under its own release and checks;
that dependency does not make the example itself a passed live test or a
substitute for the held child-deployment workflow.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/tests/live_root_bootstrap.py](../../../../../products/cpk_server/tests/live_root_bootstrap.py), [products/cpk_server/product.docker-cloudflare.cpk.json](../../../../../products/cpk_server/product.docker-cloudflare.cpk.json), [products/postgres_server/product.cpk.json](../../../../../products/postgres_server/product.cpk.json), [products/secrets_server/product.cpk.json](../../../../../products/secrets_server/product.cpk.json).
