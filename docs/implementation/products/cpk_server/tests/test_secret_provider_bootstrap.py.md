Source: [products/cpk_server/tests/test_secret_provider_bootstrap.py](../../../../../products/cpk_server/tests/test_secret_provider_bootstrap.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite tests environment decoding and provider composition, then exercises
the actual adopted registry/resolver/client path with synthetic credential
files and httpx.MockTransport. A constructed resolution grant selects one of two
endpoint and credential references; the recorded request must use the selected
host and bearer and return SecretResolved. Selected repr checks omit provider
URLs, credential paths/tokens and returned material.

The grant is a fixture, not issued by Operations authorization, and the HTTP
response is scripted. This proves local routing/composition assertions, not a
real provider's authorization, durable custody or encryption. Temporary files
are synthetic and do not model the production owner's custody permissions.
Config repr checks also do not establish universal redaction of all fields
such as store DSNs.

Negative configuration cases cover absent registries, duplicate endpoint keys,
inline values in provider mode and the retired Docker-config selector.
Descriptor checks require provider mode without embedded registry/material
settings. Text checks exclude named obsolete helpers and require current owner
names; they cannot prove equivalent behavior is absent everywhere.

Related source: [server composition](../src/control_plane_kit_servers_cpk_server/server.py.md),
[Docker product](../product.docker.cpk.json.md),
[Docker/Cloudflare product](../product.docker-cloudflare.cpk.json.md).
