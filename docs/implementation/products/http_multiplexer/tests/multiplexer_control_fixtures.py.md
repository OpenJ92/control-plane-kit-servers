Source: [multiplexer_control_fixtures.py](../../../../../products/http_multiplexer/tests/multiplexer_control_fixtures.py).
Maintain with synthetic product authority and host ownership.

Fixtures generate independent Ed25519 static/health keys in memory and sign actual
Core grants for a fixed injected clock. No deployable private/default key is saved.
The actual factory runs on loopback port0; tests bound client reads/timeouts and
close clients, host socket and worker threads, joining from outside serve_forever.
Application body/headers can be supplied to prove real handler composition. These
helpers run through the existing owning suite, not a new gate or runtime framework.
