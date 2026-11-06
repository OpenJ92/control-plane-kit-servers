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

Kepler target review strengthened exact declaration negatives in both directions,
well-typed foreign declaration refusal before bind, an actual alternate secret
purpose, independent artifact revalidation, and late reader exceptions overridden
by stop/native death. SDK fixture shutdown is bounded through a daemon helper and
unconditionally closes the listener; stalled cleanup fails rather than hanging
this owning suite. These extend the same new laws, not SDK internals.

The first implementation gate exposed a target-fixture defect: syntactically
invalid JSON is rejected by Core ConfigurationArtifact before reaching this
product factory. At selected Core73d87e99, test_configuration_artifacts.py's
`test_paths_parser_shapes_and_secret_shaped_content_fail_closed` owns that parser
law (malformed-media cases at105–120). The product target instead uses valid JSON
`{}` with invalid receiver schema, retaining its exact ConnectorConfigurationError
assertion and the well-typed foreign declaration case. Initial red placeholders
had prevented this downstream fixture branch from running; that red did not
prove the branch was correctly constructed.

## Pending #280 declared contract targets

The new target requires public declaration and required-contract factories,
exact control slot and advertisement, empty defaults/direct deliveries, and
ordinary Core refusal of unresolved required material. Existing strict actual
configuration/token laws remain; an explicit absent-token case protects the
actual-source entrance. Missing factories are asserted inside test bodies to
preserve collection. An interface assertion failure is not evidence for later
semantic assertions. No factory implementation or test run is included in this
target checkpoint.

The #280 source checkpoint now supplies the declaration and required-contract
factories. Targets remain unchanged; actual-source token/config refusal remains
strict. These product tests were not reached by the bounded root-red run and
must pass in the full ordinary gate before acceptance.
