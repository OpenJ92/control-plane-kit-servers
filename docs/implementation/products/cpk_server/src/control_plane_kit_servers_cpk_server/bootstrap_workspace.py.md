Source: [bootstrap_workspace.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_workspace.py).

This root-installer adapter consumes already bounded private bytes and invokes
existing policy, identity, scope, key, revision and credential owners. It performs
no file, database, Docker or provider I/O. The commitment binds exact policy bytes,
explicit installer identity/key and complete public/private setup intent; the
private index separately binds the reviewed public plan digest. Hashes prove
correspondence, never administrator authority.

The actual process parser and verifier resolve the selected setup bearer, then
WorkspaceAdministrationPolicy.authorize checks the resulting full identity.
Permission requests use GrantWorkspacePermissions and require_known. Optional
management intent validates only pre-registration fields; the later enrollment
child must consume the real returned registration ID. No placeholder registration,
static grant overlay, initialization call or state machine is introduced.

The admitted snapshot hides fields from repr and keeps exact policy bytes and
canonical private administration bytes separate from credential references.
The caller translates every rejected private input into the fixed material-refused
classification without retaining private parser exception context.

The owner IdempotencyKey constructor raises InvalidOperationCommand rather than
ValueError. A narrow adapter translates that specific exception outside its
handler at all four private key sites. The private material boundary then emits
material-refused without retaining the owner exception; arbitrary RuntimeError
is not swallowed.

#347 shares the pure fixed-input projection between initialization and enrollment.
The public helper receives only plan, credential, private intent, policy and
optional principals. The distinct loader performs bounded protected-file reads
and delegates to the same pure admission function; no database or provider I/O
occurs here. Initialization adds its own target/password separately.
