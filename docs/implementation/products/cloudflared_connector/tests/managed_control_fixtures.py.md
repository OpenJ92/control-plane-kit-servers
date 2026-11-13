# Local managed connector authority fixture

Source: [managed_control_fixtures.py](../../../../../products/cloudflared_connector/tests/managed_control_fixtures.py).

Generates local Ed25519 verifier families and real Core V2 target/declaration,
request and grant values for the control socket. Derived from the established
Hello test pattern, with the connector's intended declaration authored directly.
No fixture credentials/configuration are runtime defaults or deployment evidence.
