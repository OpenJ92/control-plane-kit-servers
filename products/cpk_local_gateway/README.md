# Gateway health-transit trust

The source package provides a strict public trust configuration and a pure
Ed25519 verifier for health-transit credentials. This is separate from the
existing gateway probe endpoint; it does not add HTTP relay or change published
image descriptors.

The parent supplies workspace, gateway node, runtime, issuer and the exact
gateway health-transit public-key family. Configuration derives the audience
and permits overlapping public keys. Encode it with
`gateway_health_transit_configuration_artifact`, then construct the receiver
with `gateway_health_transit_verifier_from_artifact` from the selected artifact.
Both functions live in the product's `health_transit_configuration` and
`health_transit_verification` modules respectively.

```python
verifier = gateway_health_transit_verifier_from_artifact(selected_artifact)
accepted_request = verifier.verify(
    credential, request,
    expected_attempt_id=admitted_attempt,
    expected_target=admitted_target,
    expected_runtime_id=admitted_runtime,
    expected_declaration=admitted_declaration,
    expected_kind=requested_kind,
    now=trusted_observation,
)
```

The expected context must come from independently admitted execution/routing
state. Do not derive it from the incoming token. Verification does not establish
current approval, dispatch freshness, replay storage or workload authorization.
It reads no files and performs no network call.

Servers180 owns receiver process/HTTP relay adoption;208 owns composition
adapters; CPK1857 owns pinned receiver-trust coverage. The existing `./test.sh`
is the owning Docker gate. Source tests do not establish published-image or
live deployment acceptance.
