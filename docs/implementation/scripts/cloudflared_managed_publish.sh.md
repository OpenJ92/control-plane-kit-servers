# Managed cloudflared producer

Explicit managed selector only; historical selector stays unchanged. Requires clean source, source-bound tag, existing private package, no tag collision, and a new retained receipt directory. Acquires the owning test controller explicitly, builds one managed candidate, qualifies its exact ID through test.sh, binds/rechecks the publication tag and pushes once. Provider metadata and actual remote index/platform/config/source correspondence must verify afterward. Failure/ambiguity never triggers retry or cleanup of the borrowed candidate/evidence. Running this producer requires an artifact-specific release; source/CI approval alone does not authorize it.

Both controller and product contexts come from the exact tracked commit archive rather than the working directory. Required paths, absence of submodules and complete archived path coverage are checked; archive bytes/hash remain with the source/recipe receipt. Ignored bytecode never enters these build contexts. This does not broaden production invocation authority.

The read-only policy container explicitly uses the producer's numeric UID/GID,
which owns the newly created 0700 receipt directories and 0600 metadata files.
This applies to all four policy calls, including qualification receipt checking.
It preserves read-only mounts, no network, no-new-privileges and cap-drop ALL;
it does not broaden file modes or grant DAC capabilities. The existing candidate
qualification controller has a separate Docker-socket execution contract and is
unchanged. Wrapper application source and the v2 evidence schema are unchanged.

Focused owning-route tests model a nonmatching image identity, require explicit
owner alignment for all policy invocations, verify private input modes and the
isolation flags, and stop before build/push on mismatched identity. These command
doubles prove orchestration, not Linux kernel DAC or the cause of release
40074073227. That run's preflight-policy failure exposed the missing identity
contract; its retained evidence does not establish the actual process identities.

## Bounded terminal diagnostic (#191 follow-up to #322)

After receipt-directory admission, the producer installs one EXIT trap. The trap captures the original status as its first argument, disables itself, attempts an exclusive temporary JSON write and atomic rename in the existing private receipt directory, and explicitly exits with the captured status. Diagnostic failure is best-effort and cannot turn success into failure or failure into success. An existing destination is never overwritten. No record is promised before safe admission or after hard termination.

The fixed record is cpk.cloudflared-managed-producer-diagnostic.v1 with source_commit, stage and exit_code. Stage is the last boundary ENTERED, not the last successful operation or proof of provider state. The existing metadata helper selects only its three fixed call-site prefixes; remote-verification is restored after published metadata/policy before subsequent manifest/config checks. complete corresponds to zero; failure stages correspond to nonzero. No journal, command arguments, exception text, API response, credentials or raw log bytes are recorded. No new provider requests, retries or cleanup are introduced. Future publication remains separately authorized.
