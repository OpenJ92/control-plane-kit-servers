# Public Topology Client

The `cpk` command is an ordinary-host HTTP client for an existing cpk-server.
It submits complete desired graphs, displays the server's plan, requires exact
plan-bound authorization, and sequences only the accepted public commands.
It does not plan graphs, access Docker or providers, bootstrap workspaces, or
infer recovery.

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
