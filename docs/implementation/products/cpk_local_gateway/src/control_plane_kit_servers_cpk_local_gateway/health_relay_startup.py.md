# Gateway process health configuration loading

Source: `products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/health_relay_startup.py`.

The process opens the two fixed selected configuration files, verifies regular
files, reads at most each schema limit plus one byte, decodes actual contents and
constructs the gateway verifier/relay. There is no catalogue/default key fallback.
The relay requires both files to agree on workspace/gateway/runtime. An integer
wall-clock sample is injected at each transit admission; no renewal or skew.

File paths belong to trusted process composition; this loader is not a sandbox
for hostile filesystem owners. Missing or malformed files prevent serving. No
private key or secret-provider operation is involved. Actual temporary-file/main
loading is covered by owner tests; Docker mount delivery evidence remains the
previous #156 owner evidence, not a claim newly made by this loader.
