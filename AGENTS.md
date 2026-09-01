# control-plane-kit-servers

Canonical contract: `cpk-agent-contract/v1`

Source: [CPK #1741](https://github.com/OpenJ92/control-plane-kit/issues/1741).
This root guide carries the shared contract needed to work in this repository
without another checkout. Repository-local rules below may tighten the shared
contract; they may not weaken authorization, Docker-only validation, truthful
uncertainty, test ownership, or GitHub-memory requirements.

## Shared Product Boundary

CPK is a human-authorized, AI-assisted infrastructure control plane. Providers
own external runtime truth. CPK owns topology, inspectable plans, execution of
approved actions, durable history, and truthful bounded reports.

- Provider reads and bounded reporting may be automatic.
- Consequential mutation requires an inspectable plan and appropriate user
  authorization.
- Destructive cleanup, public exposure, cost or capacity changes, credential
  changes, cross-provider movement, adoption, and ambiguous retries require
  explicit approval.
- Never blindly redispatch an interrupted or ambiguous external mutation.
- Never fabricate success, graph advancement, ownership, or cleanup. Preserve
  uncertainty until authoritative evidence resolves it.
- Do not assume autonomous recovery, compensation, failover, or adoption.

After bootstrap, topology-producing capstone actions enter through authenticated
cpk-server HTTP or MCP. Direct Docker, database, provider, private-service, or
source-live orchestration may diagnose behavior but does not earn public
capstone acceptance.

## Durable Memory And Collaboration

GitHub issues, PRs, and material comments are the durable project memory.
Commits, hashes, local logs, `/tmp` packets, inventories, task messages, and chat
are supporting coordinates only. Record material decisions, releases, stops,
evidence meaning, reviews, and dependent handoffs on the governing issue or PR.

When roles are assigned, North coordinates scope, authority, topology, and
merge disposition; Vale implements the bounded change; Meridian reviews
independently and reports findings-first `PASS` or `HOLD`. Every assignment and
handoff names the governing GitHub artifact, repository/base/destination,
scope, owning suite and prerequisites, authority limits, stop conditions, and
next reviewer. Silence is not approval.

Keep implementation and review proportional. Tests prove this repository's
observable boundary; they do not recreate Core or Operations state machines,
police helper names or source layout, or turn fixture examples into runtime
invariants. Review blocks only concrete correctness, ownership, public-contract,
security/authority, durable-data, destructive-operation, or evidence defects.

## Shared Validation And Stops

All executable validation uses this repository's established Docker-backed
`./test.sh`. Host work is limited to source, Git/GitHub, and invoking repository
commands. Do not use host Python/PostgreSQL, venvs, host `pip`, alternate
databases, shims, or custom wrappers. If the suite or a documented prerequisite
is missing, cannot start, or fails for apparatus, stop and ask; do not
improvise, silently retry, rebaseline, or repair shared state.

One-shot wrappers, leases, full inventory sealing, provider mutation, and
destructive cleanup require an explicit issue-specific release. Before a long
Docker gate, push a candid unvalidated checkpoint. Stop when ownership,
authority, base/destination, prerequisites, external-effect outcome, or the
GitHub/local decision state is uncertain.

This repository owns reusable OCI server products and their descriptors for
`control-plane-kit`. It is not the algebraic core. It may import the pinned
`control-plane-kit-core` package to express values, descriptors, socket
contracts, process handoff contracts, and tests. Core never imports servers.

## Repository Law

- one product implementation lane owns one directory; explicit descriptor variants may share that lane.
- Catalogue imports values, not applications or stores.
- cpk-server and Hello have different roles and neither substitutes for the
  other.
- `products/cpk_server` is the control-plane process wrapper.
- `products/hello_server` is the first ordinary reusable server product.
- Do not create implementation directories before the issue for that product
  opens.
- Do not use broad Docker prune. Inspect Docker resources first and preserve
  every unrelated or foreign container, network, volume, image, and mapping.

## Issue Loop

For every non-trivial issue, use this calibrated loop:

```text
current issue and public contract
  -> inspect the owned source and tests
    -> bounded implementation and proportional tests
      -> authoritative Docker-backed ./test.sh
        -> concrete review
          -> decision log and dependent handoff
```

Use behavioral law cards, frozen-test translation, and focused target-red
evidence only for an explicitly governed migration/parity issue or when a
focused failure is needed to establish causality for missing behavior. Do not
copy tests mechanically, weaken assertions, add unjustified skips, hide tests
from collection, preserve obsolete structure merely because a fixture
referenced it, or point successor tests at a frozen implementation.

## Testing

Use the repository's authoritative Docker-backed `./test.sh`. Its image and
package coordinates are repository-owned prerequisites. Do not replace it with
host execution or an ad hoc focused container command.

## Product Ownership

Each product implementation directory owns its descriptor declaration or explicit descriptor variants, implementation,
entrypoint/process wrapper, Dockerfile or image build material, verification
contracts, image publication evidence, tests, examples, and learning notes.

Shared support requires evidence from two products or an explicit bootstrap
exception recorded in the issue and decision log.

## Security

Descriptors, logs, events, examples, and MCP/HTTP errors must not contain secret
values. Images must run with least privilege, explicit networking, explicit
ports, bounded logs, and owned cleanup evidence.
