Source: [server.py](../../../../../../products/secrets_server/src/control_plane_kit_servers_secrets_server/server.py).
Maintain alongside the product process composition.

The import-safe factory reads one independent Secrets V2 snapshot and optional
sample companion using the existing SDK reader, then binds the original product
check/socket/port. Only after public admission does it call the real Secrets
import-safe factory once, supplying that snapshot and binding. Explicit mapping
cannot hide/redirect the SDK's process-environment companion. Malformed/missing
opt-in raises a fixed provider error before the factory's private work. The
product never imports the legacy eager upstream server. Ordinary absence
supplies no binding. Precise sample time remains separate from V2 time.
