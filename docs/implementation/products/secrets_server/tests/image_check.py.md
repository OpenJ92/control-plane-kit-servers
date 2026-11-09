Source: [image_check.py](../../../../../products/secrets_server/tests/image_check.py).
Maintain with the #163 focused Secrets image action.

Runs read-only with no network inside the built product, checks actual installed
Secrets/Core/SDK direct-URL origins against unchanged coordinates, imports the
packaged product launcher from /opt/cpk-secrets-product, and runs pip check.
Only public origins and fixed pass/failure fields are emitted. Main process
startup, custody, signed checks and cleanup remain separate image-smoke evidence.

Optional --parent changes ONLY the expected Secrets origin to exact57e4fc61;
Core976 and SDKd61 keep the unchanged coordinates. It also binds the actual
imported provider_policy.py to the installed distribution and exact public Git
source hash. This is public source provenance, never a credential fingerprint.
