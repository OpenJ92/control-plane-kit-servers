# Managed connector configuration and health laws

Source: [test_managed_connector.py](../../../../../products/cloudflared_connector/tests/test_managed_connector.py).

New-law targets under Servers #188, derived from reviewed single-node product,
SDK reuse and bounded native-readiness plan. Tests use actual Core configuration
values and SDK-signed receiver credentials; test-only generated authority is never
a product default. The fixture declares the intended interface independently of
the deliberately unimplemented application factory, allowing causal-red failures.

Laws: only control:8000 provider, scoped token-file delivery, unchanged historical
image; reject foreign/missing readiness declarations; healthy/disconnected/unknown
mapping; native death/stop overrides late success; single active native read;
unknown on unexpected read failure; SDK denial before native I/O and correlated
results. The real SDK host test does not substitute for process/image evidence.
Lifecycle and image tests remain required before implementation completion.
