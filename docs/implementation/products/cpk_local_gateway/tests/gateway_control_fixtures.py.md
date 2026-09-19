# Gateway self-health fixtures

Source: `products/cpk_local_gateway/tests/gateway_control_fixtures.py`.

Synthetic product-local public trust and actual #180 relay configuration feed
the real SDK composition. Credentials use Core grants and synthetic Ed25519
keys; no copied verifier or durable authority service is present. Downstream
transport deliberately returns503 and records calls. The topology builder copies
the complete returned source contract, including verification and configuration
artifacts, into actual Core graph values without stripping obligations. No
fixture creates containers, performs provider effects or establishes live TLS.
