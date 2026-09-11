Source: [products/cpk_server/tests/test_source_live_gateway_denials.py](../../../../../products/cpk_server/tests/test_source_live_gateway_denials.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

The coordinate cases construct an in-memory gateway descriptor using a
digest-shaped reference and canonical source-commit text, assert local source
bytes did not acquire the fixture digest, and reject a mutable tag or branch
name. They do not query a registry or establish image/source correspondence.

The transaction witness uses a synthetic integer sequence to calibrate equal
positive measurement deltas, subtract its own measurement overhead and reject
an unexpected delta or unstable calibration. No Postgres connection or live
gateway request runs here. Detecting a delta is not universal proof about the
absence or attribution of target I/O under concurrent activity.

The live denial matrix belongs to the controller; this file checks two of its
support mechanisms rather than executing the signed denial cases.

Controller owner: [source-live controller](../../../../../scripts/cpk_server_secret_provider_source_live.py).
