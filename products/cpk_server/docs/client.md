# Public Topology Client

The `cpk` command is an ordinary-host HTTP client for an existing cpk-server.
It submits complete desired graphs, displays the server's plan, requires exact
plan-bound authorization, and sequences only the accepted public commands.
It does not plan graphs, access Docker or providers, bootstrap workspaces, or
infer recovery.

HTTP requests identify the client as `control-plane-kit-cpk-client/0.1.0`.
This is a product identity, not a browser signature or an authorization grant.

## Profile

Create `$XDG_CONFIG_HOME/cpk/profiles/PROFILE.json`, or use
`~/.config/cpk/profiles/PROFILE.json`:

```json
{
  "schema": "cpk.client-profile.v1",
  "endpoint": "https://cpk.example",
  "workspace_id": "workspace-a",
  "credentials": {
    "operator": "/private/path/operator.token",
    "approver": "/private/path/approver.token",
    "worker": "/private/path/worker.token"
  },
  "state_directory": "/private/path/cpk-state"
}
```

The profile and credential files must be owned by the current user, regular
files rather than symlinks, and inaccessible to group and other users. The
credential entries are file references. Tokens never belong in arguments,
desired graphs, journals, or output.

Desired graphs may contain the secret references supported by CPK, but not raw
or resolved credential/provider-secret material. The client treats product
configuration as opaque and does not attempt to discover secrets inside it.

## Plan

```bash
cpk --profile PROFILE plan desired-graph.json
```

The client reads current workspace coordinates and passes the complete graph
unchanged to `deployment.prepare`. Preparation can create durable CPK intent
and plan records but performs no provider effects. Output includes the opaque
operation reference, exact plan reference, server plan activities, required
authorization, and destructive flag.

If the prepare response is lost, retain the desired file unchanged and run:

```bash
cpk --profile PROFILE plan --resume OPERATION_REFERENCE
```

This can only replay the exact persisted request key and the request rebuilt
from the same verified desired-file bytes. It never issues a fresh prepare key.

## Apply

Every apply names the local operation and repeats the exact reviewed plan:

```bash
cpk --profile PROFILE apply OPERATION_REFERENCE --execute-plan PLAN_ID \
  --approve-plan PLAN_ID
```

For a destructive plan, use the distinct destructive approval:

```bash
cpk --profile PROFILE apply OPERATION_REFERENCE --execute-plan PLAN_ID \
  --approve-destructive-plan PLAN_ID
```

There is no generic yes flag. The client stops rather than executing when the
plan, approval, workspace, graph lineage, revision, run, or fence differs from
the retained and freshly read public coordinates.

Each mutation is recorded before dispatch. A lost response is resolved only by
that route's documented exact request replay. Each intended execution step has
a fresh key; replay of that exact step keeps its key. Blocked, failed,
unsupported, uncertain, in-flight, unverified, or budget-exhausted work stops
without a later mutation.

## Status

```bash
cpk --profile PROFILE status OPERATION_REFERENCE
```

Status performs public GETs only. It reports planned or running work neutrally,
and returns an attention-required nonzero exit when durable truth cannot be
resolved. Local journal state locates public coordinates; it never proves
approval, execution, advancement, health, or completion.

Use `--json` on any subcommand for the closed `cpk.client-result.v1`
projection. Human and JSON output share the same result and exit categories.
Workload health and freshness are `unknown` unless an applicable public
observation supplies them.

## Private State

Invocation journals are private `0600` canonical JSON under the configured
state directory. They retain only public coordinates, bounded command replay
material, and the desired file's path/size/digest. A validated persistent lock
file is paired with a kernel advisory lock, so process death releases writer
ownership without lock-age guesses or automatic recovery.

Unresolved operation locators are not expired or deleted automatically. A
profile endpoint or workspace mismatch always stops and never rebinds the
journal. cpk-server remains authoritative for all workflow and effect truth.

## Overview and saved draft catalogue

Install the maintained server distribution from the reviewed #137 checkout:

```sh
python3 -m pip install /path/to/control-plane-kit-servers
cpk --profile PROFILE overview
cpk --profile PROFILE draft list --limit 20
cpk --profile PROFILE draft save desired-graph.json --title 'My topology'
cpk --profile PROFILE draft show DRAFT_ID --revision 1
cpk --profile PROFILE draft revise DRAFT_ID changed-graph.json --expected-head 1
cpk --profile PROFILE draft select DRAFT_ID --revision 1
cpk --profile PROFILE overview
```

Use the dependency coordinates in that checkout's `pyproject.toml`: Core and
Operations are pinned to `e3d773d022fd36e727ee1d94f4c4396b25c722c6`.
The distribution installs the existing `cpk` entrypoint and its normal server
and interpreter dependencies; no second client package is needed. Configuration
and private credential-file roles are the same as above. These installation
commands are operator instructions, not a host validation substitute.

Save prints the returned draft/revision/graph coordinates. Show prints those
coordinates and creation time; it does not print the graph or title. List emits
one bounded page and its opaque continuation; pass that JSON object with
`--cursor` to request the next page. Overview distinguishes the selected revision
from the latest head and reports only bounded public coordinates/states. It is
an observation, not an atomic snapshot or permission to act on its suggested
next action.

Each save/revise/select invocation records a public operation-session start
before its draft command. These two HTTP requests are not atomic. A rejected or
unverifiable draft command can leave a visible session; the client neither
closes it automatically nor creates a replacement. No catalogue command plans,
approves, executes provider actions, or changes the current graph. Selecting
revision 1 after revising to revision 2 is deliberate and does not select head.
A stale expected head or selection fence stops without rebasing.

If a response is lost, retain the operation reference and explicitly resume:

```sh
cpk --profile PROFILE draft resume OPERATION_REFERENCE
```

Resume uses the same request keys and original selection fences. A persisted
draft request can replay historical evidence after session closure; a new draft
request requires the returned session still be open. Completed receipts remain
historical and do not prove that their selection is current now. Graph-file
path/size/SHA must still match for unfinished save/revise replay. Do not edit or
remove that file before resolving the operation. Raw graphs and credential
contents are never written to the journal or catalogue output. The private
journal may retain the supplied draft title only to reproduce the exact request.

Catalogue receipts use `cpk.client-catalogue-result.v1` with status `recorded` or
`attention-required` (exit 4); the read commands use
`cpk.client-catalogue-read.v1`. Existing deployment `cpk.client-result.v1` and
file-based plan/apply/status behavior remain unchanged. Saved preparation and
multi-operation reporting are separate subsequent slices.

## Prepare an exact saved revision

After explicitly selecting a saved revision, prepare it through the same plan
command:

```bash
cpk --profile PROFILE plan --draft DRAFT_ID --revision 1
```

The file, saved revision, and `--resume` inputs are exclusive. `--draft` and
`--revision` must be supplied together; a revision cannot accompany a file or
resume reference. The Python facade accepts `SavedDesiredRevision(draft_id,
revision)` as the existing `TopologyClient.plan` input.

Each fresh invocation reads current workspace graph/projection and desired
graph/projection/generation fences. It sends those fences and exact draft
coordinates to the existing preparation command. Operations validates selection
and admission. This client does not fetch or republish the saved graph, select
it again, or grant execution permission.

A saved invocation uses the separate private `cpk.client-saved-invocation.v1`
journal. Its closed `prepare_request` retains `draft_id`, `revision`,
`expected_current`, `expected_desired`, `expected_desired_graph_revision`, `title`
and `idempotency_key`. Both graph/projection tuples are required. These bounded
transport records remain private and are not proof of historical admission,
approval or execution.

If the preparation response is lost, `plan --resume OPERATION_REFERENCE` replays
that exact retained request, including the original key and fences, without a
workspace reread. Later selection/head drift does not rewrite the request. A
completed preparation is inspected or applied through the existing commands;
resume does not start another preparation.

To ask whether the same selected revision is now converged, start a **new** plan
invocation. It uses a fresh key and fresh workspace fences without reselecting.
Only the server's plan and `no-changes` response establish that result. A new
plan never automatically approves or applies effects. File-v1 journals,
catalogue journals, existing approval requirements and result-v1 output remain
unchanged.

## Bounded report

```bash
cpk --profile PROFILE report INITIAL_OPERATION CHANGE_OPERATION --json
```

Supply one to four distinct operation references, including deployment or
catalogue references. `cpk.client-report.v1` is a separate envelope; existing
plan/apply/status result-v1 is unchanged. Human output is the same projection in
indented JSON when it fits the limit, with compact JSON as a bounded fallback. `observed` means the requested evidence was read, not that a run
succeeded or the workspace is currently converged.

The report separates:

- `requested`: private transport provenance, with file/saved/catalogue source;
  a catalogue receipt revision is distinct from its authoring request;
- `session`: fresh public session status and only four explicitly labelled
  server-reported saved metadata fields, without fingerprint validation;
- `association`: a fresh immutable revision-to-plan graph comparison, not proof
  of historical admission;
- `plan`, `approval`, `runs`: correlated public coordinates/statuses and bounded
  event kinds, without provider payloads or inferred health;
- `latest_overview`: a separate public observation read last, which may differ
  from all earlier operation observations.

Missing, mismatched or truncated evidence produces attention-required output.
Historical success never becomes a claim of current convergence. Current graph
coordinates do not imply a current draft revision. Collection elapsed time is
not provider freshness; `provider_freshness` stays `unknown` and
`atomic_snapshot` stays `false`.

Limits are four operations, 32 GET calls, one page per collection, two runs per
plan, ten events per run, and 256 KiB serialized output. Both CLI modes check
the actual UTF-8 stdout representation, including its trailing newline. The present composition
uses at most 29 calls and 80 events; no cursor is followed. Valid Unicode
identifiers can expand when JSON encoded, so output overflow returns an explicit
truncated shell. Credentials, graph bodies, arbitrary metadata, request keys,
file paths, titles and provider/failure payloads are omitted.

A 60-second monotonic scheduling budget prevents starting another read once
exhausted, including the final overview. This is not a hard total duration:
the existing transport uses a 30-second socket timeout by default and cannot
cancel an entire in-flight read at the scheduling boundary. The report never
calls a command route, replays an operation, or writes its journal.

## Install and configure the maintained client

Use Python 3.12 or newer. This source checkpoint contains the maintained client
and report; its normal metadata pins Core/Operations to
`e3d773d022fd36e727ee1d94f4c4396b25c722c6` and Interpreters to
`ed5dd9ed28193c60c76e96d3380f6e4812d4b3a1`:

```bash
git clone https://github.com/OpenJ92/control-plane-kit-servers.git cpk-client-source
cd cpk-client-source
git checkout 19697a79b00666bc0969f244689ba6a15b47f9e4
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
cpk --help
```

The exact CPK repository coordinates are reproducible; transitive third-party
packages still use the declared version ranges, not a complete lockfile. The
current distribution includes server dependencies; this does not start a server
or grant runtime authority. Access to private source repositories must already
be configured through your normal Git/package credentials.

Create a private configuration directory and copy **already issued**, scoped
credential files from their protected custody location. Do not paste tokens into
commands or reports:

```bash
umask 077
mkdir -p "$HOME/.config/cpk/profiles" "$HOME/.local/state/cpk"
chmod 700 "$HOME/.config/cpk" "$HOME/.config/cpk/profiles" "$HOME/.local/state/cpk"
install -m 600 /protected/issued/operator.token "$HOME/.config/cpk/operator.token"
install -m 600 /protected/issued/approver.token "$HOME/.config/cpk/approver.token"
install -m 600 /protected/issued/worker.token "$HOME/.config/cpk/worker.token"
```

Create `~/.config/cpk/profiles/PROFILE.json` using the profile shape above, with
your authenticated server endpoint, existing workspace ID, and **absolute**
credential/state paths; then `chmod 600` that file. Operator, approver and worker
roles remain separate. No token minting, workspace bootstrap, provider changes
or new network exposure is performed by client installation.

## Complete saved-topology operator loop

This is the acceptance procedure, not an executed live result. Start with an
existing authorized workspace, its registered products/runtimes, and retained
valid graph inputs: `initial.json` for the representative Hello deployment,
`changed.json` for the reviewed change/removal, and `teardown.json` preserving
anything outside the explicitly owned application resources. Use the existing
[Hello authoring and ownership guidance](../../../docs/persistent-hello-demo.md)
and [servers #123 convergence evidence](https://github.com/OpenJ92/control-plane-kit-servers/issues/123).
Do not regenerate unrelated nodes from a newer descriptor or interpret an empty
graph as permission to delete everything. The graph inputs are owner-authored
values; this client does not build another convergence scenario matrix.

Inspect and save the initial intent:

```bash
cpk --profile PROFILE overview
cpk --profile PROFILE draft save initial.json --title 'Reviewed Hello deployment'
cpk --profile PROFILE draft list
cpk --profile PROFILE draft show DRAFT_ID --revision 1
cpk --profile PROFILE draft select DRAFT_ID --revision 1
cpk --profile PROFILE plan --draft DRAFT_ID --revision 1
```

Copy actual returned draft, operation and plan IDs; names in capitals here are
placeholders, never preapproved identifiers. `draft show` returns coordinates,
not a replacement graph/title editor. Read the prepared plan's activities,
required scope and destructive flag. Review the exact affected identities,
network exposure, capacity/cost and preservation of unrelated resources. If the
plan differs from intended ownership, stop and revise the graph instead of
approving it.

Only after approving that exact non-destructive plan:

```bash
cpk --profile PROFILE apply INITIAL_OPERATION --execute-plan INITIAL_PLAN \
  --approve-plan INITIAL_PLAN
cpk --profile PROFILE status INITIAL_OPERATION
cpk --profile PROFILE report INITIAL_OPERATION --json
```

Prepare the change as another immutable revision. `--expected-head` names the
head actually inspected; head conflicts require renewed inspection:

```bash
cpk --profile PROFILE draft revise DRAFT_ID changed.json --expected-head 1
cpk --profile PROFILE draft show DRAFT_ID --revision 2
cpk --profile PROFILE draft select DRAFT_ID --revision 2
cpk --profile PROFILE plan --draft DRAFT_ID --revision 2
```

Inspect this new plan independently. For a removal, obtain explicit destructive
permission for this exact plan before the separate call:

```bash
cpk --profile PROFILE apply CHANGE_OPERATION --execute-plan CHANGE_PLAN \
  --approve-destructive-plan CHANGE_PLAN
cpk --profile PROFILE status CHANGE_OPERATION
cpk --profile PROFILE report INITIAL_OPERATION CHANGE_OPERATION --json
```

After successful advancement, ask for a fresh converged no-op using the same
selected revision. Do not select again and do not resume the old preparation:

```bash
cpk --profile PROFILE plan --draft DRAFT_ID --revision 2
cpk --profile PROFILE report NOOP_OPERATION --json
```

The fresh invocation uses fresh fences/key. Only its server-produced no-changes
plan establishes the no-op; it needs no approval or execution. A lost response
instead uses `plan --resume THE_SAME_OPERATION` with its exact retained request.
An uncertain effect is inspected through status/report and owner evidence,
never blindly redispatched as a fresh command.

Teardown is a new, separately reviewed intent and permission decision:

```bash
cpk --profile PROFILE draft revise DRAFT_ID teardown.json --expected-head 2
cpk --profile PROFILE draft select DRAFT_ID --revision 3
cpk --profile PROFILE plan --draft DRAFT_ID --revision 3
```

Review retained control-plane, shared runtime, ingress, secret-reference and
unrelated application ownership before granting destructive approval. Only if
that exact teardown plan is authorized:

```bash
cpk --profile PROFILE apply TEARDOWN_OPERATION --execute-plan TEARDOWN_PLAN \
  --approve-destructive-plan TEARDOWN_PLAN
cpk --profile PROFILE status TEARDOWN_OPERATION
cpk --profile PROFILE report INITIAL_OPERATION CHANGE_OPERATION NOOP_OPERATION TEARDOWN_OPERATION --json
```

This teardown does not authorize deleting the control-plane installation,
database volume or shared infrastructure. Provider-owned inspection is still
needed to establish external cleanup/health. The report truthfully limits itself
to its correlated public evidence; parent #1752 live acceptance, final integrated
review and roadmap promotion remain separate gates.
