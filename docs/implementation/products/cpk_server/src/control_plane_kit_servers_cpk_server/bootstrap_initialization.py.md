Source: [bootstrap_initialization.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_initialization.py).

#346's socket-free helper admits only fixed protected files. It reverifies the
public plan, #345 private commitment and actual setup bearer identity, selected
database endpoints, trusted installer target projection and installed Operations
archive/schema correlation before database access. The projection is controller
custody evidence, not a cryptographic proof or authority supplied by database
possession. Policy bytes, actor/key, credentials and private intent never enter
its bounded progress or exceptions. Ambient PG settings are refused.

Initialization opens a fresh idle autocommit connection with explicit loopback,
port/database/user/password and bounded connect/statement/lock timeouts. The
existing owner's require_empty=True transaction must commit and the connection
close before schema acknowledgement. WorkspacePermissionCommandService then
uses a separate ordinary UoW. Exact fresh receipt type, installation/full actor,
key and result/readback equality are checked before final acknowledgement.
Default process startup and its receipt guard are untouched. Schema and binding
commits are separate; a lost acknowledgement is not rollback or permission to retry.

The distinct inspect command uses only the owner read service over an explicitly
read-only connection. Matching, missing and conflict are bounded observations;
query/schema/connection failure remains unknown. It never invokes either mutation
owner. Protected progress uses a new private directory beneath a numeric-owned
0700 parent on the controller's dedicated persistent progress volume, bounded atomic writes and
fsync; a preexisting directory refuses rather than replaying work. No raw receipt
or exception context is projected. No installer/API/SQL selector is exposed by CLI.

Source checkpoint is unvalidated. Existing PostgreSQL component evidence targets
physical commit versus acknowledgement loss separately; full public root setup
and dynamic apply remain #347, and the public guard is retained.

Run 40703084900 exposed a false acknowledgement after the real PostgreSQL fixture
closed the schema connection before COMMIT. Psycopg 3.3.6's transaction exit returns
without sending COMMIT when its transport is already bad; absence of an exception
alone was insufficient. After the owner returns, the helper now requires the
connection still open, autocommit true and transaction state IDLE before closing
it and writing schema acknowledgement. Unverified completion leaves schema pending
and does not enter initialization. The existing real-connection loss target and
independent catalogue assertion are unchanged; no new SQL, owner API, retry or
claim of independent durable verification is introduced. Correction is unrun.

#347 reuses the shared fixed private input projection/admission. Database target,
password, installed schema correlation and initialization transaction behavior
remain specific to this helper. Accepted #346 evidence is recorded on its issue;
new shared-source changes require their own owning gate.
