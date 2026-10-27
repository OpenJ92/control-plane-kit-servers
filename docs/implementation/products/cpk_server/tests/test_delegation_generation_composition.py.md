Source: [test_delegation_generation_composition.py](../../../../../products/cpk_server/tests/test_delegation_generation_composition.py).

For #341, the existing static assembly fixture explicitly sets
`config.workspace_authority = None`, like its existing managed-health default.
This prevents an unrestricted Mock from inventing dynamic configuration. Its
explicit/default principal-authorizer forwarding assertions remain unchanged.

#315 target tests for the small provider bridge and real owner factory. A typed
Operations grant and real registry select the public client's configuration;
the client double proves exact arguments, one call, unchanged result and no retry.
No credential file is created or opened. Real provider composition forwards the
registry and transport into the effect ports. A separate real _operations_application
test proves explicit authority reaches the factory and the default remains None,
with only schema/provider effects and factory construction replaced. Factory tests
cover all four generator/authority combinations and actual owner construction.
The 400/501 distinction observes route-adapter availability: its text parser
rejects empty issuer before command construction, authorization or UoW entry.
It does not execute generation command laws. Provision is 501 in every combination.

Implementation review additionally requires the generator to share the existing
custodian's public client-policy object, alongside registry and transport; one
identity assertion protects that composition without reimplementing client policy.

Run 40012073568 reached the real factory but all four availability subcases errored
before their assertions: the fixture supplied Mock instead of the required exact
HealthReceiverDecoders value. The correction uses the existing empty immutable
HealthReceiverDecoders(()) prerequisite, as disabled production composition does.
It changes no trust check, production source or availability/zero-work assertion.
Those four subcases and later gate stages remain uncredited until a completed run.

The initial test-only checkpoint earned intended missing-interface/connection red
in run 40009978175. Implementation now supplies those interfaces, but later checks
remain uncredited until they execute in a successful owning run. Only normal
Docker-backed ./test.sh/PR CI supplies evidence; no alternate harness is introduced.
Operations owns durable state, provider-registration and authorization algorithms;
these tests do not reproduce them or claim connected-provider/live proof.
