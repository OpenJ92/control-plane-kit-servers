Source: [gateway_target_qualification.py](../../../scripts/gateway_target_qualification.py).

#2089 strengthens the existing transient trust projection: preserve the actual
parsed full gateway receiver target when the selected nominal Operations DTO
declares that optional field. Older actual constructors remain supported; no
exception-triggered retry or decoder registry is added. SQL's actual owner DTO
requires the full matching target; legacy health behavior stays unchanged.

The existing pure source shell gains a named `gateway-target` cohort phase under
normal `./test.sh --gateway-target-source-qualification`. Inputs are Core, Ops,
Interpreters checkouts, exact Core/Ops40-hex revisions and `legacy` or `full`.
It archives those exact sources, retains Interpreters2e2, checks import roots,
and runs the explicitly named cohort's test class in the ordinary image without
network or Docker socket. This is source compatibility, not the default package
gate or SQL execution. Existing source phases and installed pins are unchanged.

Earlier context: Core054e/Ops71db actual constructor, selected issuer/key and
graph-role identity survive. New context: Core/Ops5fe905f4244a25e5cf0f1b3ea388c49d80efc7f7
reviewed route/trust contract, full target survives; actual public
PreparedPostgresReadinessRoute accepts a matching selected decoder result and
refuses a same-node/different-receiver result from a changed selected transit
artifact. Both use actual owners, not a replacement constructor/service double.
This metadata law does not validate original Wait fulfillment or dispatch.

Dry run found the current decoder erases receiver_id; the new owner therefore
refuses congruence. Target-red must fail on the omitted full target with imports
and actual new constructor available, then turn green with the same tests.
No new public protocol, schema, network exposure, secrets, persistence mutation,
approval, current advancement or run/history claim. Owned source exports only
are cleaned. Retained profile semantics and runtime producer remain separate.

Target-red completed with28 support tests and the2 new-cohort tests: the full
target was None and the real owner route constructor refused that missing join,
not an import/collection failure. SHA256:
`ba3eb6d9ca51462b8c96f9314f4a05dd57f13ad54e6e5fcc24ae7b2e54fe027c`.
The same2 new-cohort tests passed after the decoder's bounded field projection,
including positive route construction and refusal of the actual changed transit
decoder result. Green log SHA256:
`d343ac7f86bc859da8f20d1ab40fa3558633d4944a43e87a9ac078f7b0090d5c`.
Both runs used exact reviewed Core/Ops5fe905f4, no retained plans. The separate
legacy cohort used actual Core054e/Ops71db and passed its constructor/selected
trust law, log SHA256
`4075e0886574eb8ef101c98e80a4f317b0ed87fc7c24a7d0d30fa0e2fd5f10f0`.
All commands used the repository test.sh entry point, and source
archive cleanup was verified. This closes decoder metadata compatibility only;
it does not unlock the full-plan rerun without the actual original Wait producer,
native private-byte/process/route/signing checks and committed SQL evidence.
