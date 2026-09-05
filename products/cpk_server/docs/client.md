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
