Source: [live_postgres_image.py](../../../../../products/postgres_server/tests/live_postgres_image.py).

#390 sets the shipping empty-data initdb host policy to SCRAM. The same fresh
fixture retains its local-socket initializer/sentinel checks and repeats the
TCP correct/wrong/no-challenge probes plus signed readiness after restart.
A separate fresh volume overrides only initdb host auth to trust; its independent
no-challenge SELECT1 must succeed before forced-SCRAM and signed UNKNOWN prove
refusal. Neither fixture modifies existing data or a retained installation.
Each auth phase observes the management listener and mints its signed token
after that boundary, so initialization delay or an expired earlier token cannot
substitute for the intended auth observation.
The supported exact-password claim is a nonempty UTF-8 value within the existing
file bound, with no NUL, CR or LF. File-format trailing LF bytes are stripped;
the positive fixture includes one. A logical original credential ending in LF
is therefore not byte-equivalent, as the unit counterexample proves. Embedded
newline/CR are outside this qualification; the existing parser is unchanged.

#2089 adds an authentication qualification after the existing native SQL/listener
gate on the unmodified shipping fresh-init recipe. It records only a bounded
selected psql version and success booleans for exact SELECT1 with correct/wrong
synthetic passwords and a require_auth=none control on the same loopback target,
plus the signed readiness outcome. It never changes HBA, retained data or a live
installation. A no-challenge shipping listener is a product HOLD, not readiness
qualification; no SQL fulfillment or deployment acceptance is inferred.

The original source-built ladder also accepts an explicitly borrowed published
artifact. Selection precedes fixture creation; all containers use the resolved
immutable ID. The lifecycle/retained-row checks and native-listener-before-SQL
ordering remain shared. Resource cleanup is inside exercise's finally; borrowed
fixture cleanup and ownership-aware image cleanup complete before success output.
Borrowed images are never removed, including on failure. Source image deletion
additionally checks the tag still identifies the owned image.
Before fixtures or lifecycle effects, existing named or labelled containers,
volumes and networks refuse without adoption or cleanup. Only newly returned
objects from the admitted invocation enter cleanup lists.
After image reload, lifecycle admission accepts omitted, null or empty-list
entrypoints, matching initial published-artifact admission. Nonempty and malformed
entrypoints still refuse before network, volume or product-container creation.
See [artifact procedure](../../../../managed-postgres-artifacts.md).

The approved delayed-management startup contract removes the fresh-init
UNKNOWN assertion that previously depended on the temporary initialization
server's SQL sleep. Authentication denial, authenticated HEALTHY SQL readiness,
retained data, native failure, restart and crash recovery checks remain. SQL
UNKNOWN classification is proven by owner tests, not claimed as a live recovery
phase. The listener observation requires the selected child's proc metadata to
be available under uid70; actual image execution remains the integration proof.

The existing capped failure tail also projects a numeric refused lock PID from
one strictly parsed native hint. States are absent, one, ambiguous, invalid,
truncated or unavailable; only one carries a PID. Parsing requires printable
ASCII, a bounded line and decimal PID range, the data-lock refusal marker and
the exact hint grammar. One adjacent native FATAL/HINT pair must use the supported
UTC timestamp/emitter prefix and the same emitting PID. Embedded/copied hints,
different emitters, reordered/unassociated records and unsupported formats refuse
projection; multiple refusal or hint records never select one. Reaching the requested
128-line tail limit conservatively reports truncated because prior hints may
have been omitted; byte truncation also forbids a unique PID claim.

No raw hint, directory, argv or environment is emitted. This is a projection
of a message, not observed liveness, ownership or root cause. Parser errors retain
the original assertion and cleanup paths. No new process, thread, Docker call,
stderr pipe or product instrumentation is added.

#359 retains `native_lock_emitter_pid` from the already validated matching native
FATAL/HINT prefix alongside `refused_lock_pid`. Only status `one` carries the two
bounded integers; absent, invalid, ambiguous, truncated, unavailable and scanner
failure leave both null. Equal values remain honestly represented rather than
rejected using an unverified assumption about the selected native build.

A differing pair rules out simple equality of the emitting PID and the PID named
in that observed hint. It does not identify PID7's live owner, a reused namespace
identifier, a wrapper thread or another postmaster, nor establish PGDATA ownership
or safe lock removal. Exact native version/entrypoint association remains a
separate evidence gap for failed PR358 run41011530872. Historical #277 acceptance
preserved unexplained recovery uncertainty; this field does not fix recovery.

The existing parser/projection tests cover numeric distinctions/bounds, all null
states, redaction and preservation of the original assertion/cleanup. No new log
read, process, thread, timing, native behavior or recovery assertion is introduced.
Source validation does not release a recovery rerun. Do not loop on emitter-only
sampling: after any separately authorized observation, record the comparison and
stop if instantaneous PID/TID ownership still requires a separately reviewed
observation or explicit uncertainty disposition.

The selected product can also emit one separate `postgres-server roles` record
after ordinary native-exit cleanup. The process owner captures its already-created
child/entrypoint PID, owner PID, existing management-thread native ID and explicit
entry/ended/alive observations before cleanup. It adds no process, thread, exec,
startup gate or pipe. Field reads are not atomic, and their ordering does not
establish who existed at PostgreSQL's lock check. The original lifecycle record,
failure precedence, startup and shutdown decisions remain unchanged; collection
and output failures are best-effort and cannot replace the primary failure.

The witness consumes that record only through the existing capped tail. Exactly
one closed six-field record is accepted; IDs are nullable positive bounded ints,
states are nullable bools. Missing, duplicate, malformed, truncated and unavailable
records remain explicit unknowns. Numeric child/emitter and management/refused-PID
comparisons stay separate. A matching ID with ended/unknown state is not a live
collision claim. Even a recorded live matching role only names a candidate; it
does not establish historical causality. Nonmatch excludes only that recorded
role's numeric identity, not other tasks or historical reuse. Green remains
prospective non-reproduction, with no automatic repeat or recovery action.

Failure identity includes bounded container/image IDs from refreshed attrs, a
closed witness phase, source revision/dirty state from the launcher's receipt,
and the declared immutable base read from the selected Dockerfile. These bind
observations and declarations without claiming measured native-version or
entrypoint bytes. Raw attrs, logs, paths, environment and credential values are
not exported. The separate shell summary below does not certify Python-owned
resource absence; the normal final residue audit retains that responsibility.
