Source: [root_commissioning.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/root_commissioning.py).

#301 implements explicit offline first-root read trust. `plan_root_commissioning`
validates a closed bounded intent, reuses installation identifier laws, derives
coordinates from actual product declarations and binds the immutable preparer
image in a canonical digest. Planning allocates no IDs/keys and opens no custody.

`prepare_root_commissioning` verifies that exact plan and destination before
entering private custody. A directory fd anchors no-follow relative file access;
exact owner/modes, regular single-link files, bounds and stable-read metadata are
required. A fixed nonblocking flock serializes this directory only. Pristine is
empty or just a safe empty lock. Unknown or incomplete layouts hold unchanged.

The interpreter persists/fsyncs intent and the directory before two independent
receiver UUIDs are allocated. It persists/fsyncs the receiver manifest and
directory before generating either Ed25519 key. Exactly two purposes are admitted:
surface-read and health-read. Opaque public key IDs are independent of receiver
identity. Both receivers share one public family per purpose; private halves stay
in offline custody. Actual Core values and CPK/Secrets product factories own
configuration construction and validation. No parent context, managed signer,
registration, provider credential or Operations authority is synthesized.

Public key IDs prefix fresh entropy with `key-`, preserving Core's required
alphabetic first character even when the entropy begins in a digit. SOURCE
review caught the unprefixed form before execution; a strengthened real-factory
regression forces zero-leading entropy and verifies exact reuse.

Private PEM files are exclusively created at 0400. Public/intent/receiver files
are 0600. All file writes and directory entries are flushed before completion;
persisted own-key/public correspondence is checked before complete.new is written
and synced, renamed to the absent complete.json under the lock, and the directory
synced again. This is not a multi-file transaction. Failure preserves evidence;
there is no automatic continuation, deletion, overwrite, repair or remint.

Completed reuse verifies exact layout, immutable intent, public artifact bytes,
receiver IDs, private/public correspondence and completion metadata, then returns
the same public result without writing. Completion stores public hashes only,
never private hashes. Own saved private keys are read solely for correspondence.
All implementation/closure errors cross a fixed detached exception boundary;
CLI output and argument errors are bounded and do not echo supplied payloads.

The CLI's explicit --host-state is a transport binding: it must equal the saved
host intent while --state names the mounted directory. It does not rewrite the
plan or relax the public library's exact-path rule. The launcher owns the actual
mount correspondence. No network, Docker SDK, graph or store access occurs here.

Validation: reviewed 24-target checkpoint proved causal red in normal hosted run
39663226908; implementation is pending independent SOURCE review and full owning
green. Tests use real files/crypto/locks/CLI and narrow OS failure injection.
Production custody/image qualification remains a separate approved action.
