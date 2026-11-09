Source: [image_check.py](../../../../../products/secrets_server/tests/image_check.py).
Maintain with the #163 focused Secrets image action.

Runs read-only with no network inside the built product, checks actual installed
Secrets/Core/SDK direct-URL origins against unchanged coordinates, imports the
packaged product launcher from /opt/cpk-secrets-product, and runs pip check.
Only public origins and fixed pass/failure fields are emitted. Main process
startup, custody, signed checks and cleanup remain separate image-smoke evidence.

Optional --parent uses a sealed local Git export at exact57e4fc61/tree248bc639;
Core976 and SDKd61 keep unchanged public origins. seal-parent follows the local
source/blob pattern from installer b46d471, checking every tracked input blob,
the complete package and exact21-file context before installation. The public
seal includes the final context inventory and hashes. Finished-image provenance binds all actual
installed source and RECORD hashes plus the imported policy's exact public source
hash. Its file:// origin remains truthful; this is not credential fingerprinting.
