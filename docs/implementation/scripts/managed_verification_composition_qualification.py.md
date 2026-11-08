Source: [managed_verification_composition_qualification.py](../../../scripts/managed_verification_composition_qualification.py).

Three source-only nominal boundary laws for #2089. Imports the actual selected
Operations supplied-record fixture; no duplicate durable semantics, fake
accepted invocation or SQL result. Constructs real native executors and actual
RuntimeAdapterRegistration without executing them. Resolver/transport calls are
forbidden in this phase. Tests preserve exact original binding/role/route/artifact
values, exact shared registration/support options, and nominal/crossed-product
refusal. The owning named test.sh phase records exact dependency source commits,
uses a socket-free readonly controller with no network and removes source exports.
This is not approved-run acceptance, provider qualification or installed SQL proof.
