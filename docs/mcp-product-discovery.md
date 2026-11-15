# Standard MCP product discovery — #417 / #404 / #413

This slice connects existing workspace product reads to the standard SDK
catalogue. It does not expose topology writes. Meridian cleared this bounded
scope after the c5fc9ae source trace; #408 remains design-only pending its
owner-side reference/instance input and lost-reply contracts.

## Decision log

- Chosen shape: add the existing Core read.products/list_registered_products
  and read.product-detail/get_registered_product bindings to the curated
  StandardMcpAdapter. Existing application dispatch, CpkServerReadService and
  product-directory projection remain the owners. The standard catalogue now
  has20 reads and its existing prepare command; the grandparent profile remains
  exactly four reads and refuses both new tools, including direct calls.
- Important shape: list arguments are workspace_id, optional limit1–100 and
  the owner's unmodified scoped after cursor; detail takes workspace_id and
  an exact64-character lowercase descriptor digest. Output is the unchanged,
  bounded owner result. No product values or versions are embedded in guidance.
- Why: an agent needs current authorized workspace data to discover products.
  Stable SDK instructions explain which tools to call, provider/requirement and
  configuration shapes, noncanonical readback, revoked status and authority.
  Labels/descriptions are explicitly untrusted data. Profile-specific guidance
  does not advertise hidden product tools to the G4 client.
- Alternatives rejected: exposing all Core bindings, relaxing G4, fetching a
  catalogue URL, exporting canonical private-capable documents or reconstructing
  one from its display, adding a new read owner or an arbitrary HTTP proxy.
- Behavior: directory pages contain active products. Exact detail may report a
  revoked registration; preserve that visible historical status, without
  admitting it for new authoring. The pinned reference remains authoritative;
  display projections remain noncanonical and omit configuration/material values.
- Handoff: #404 owns further read families; #413 grows factual guidance. The
  two-product recipe/save workflow and separate session-start/first-save loss
  correlations stay with #408 owner design. No ordinary-agent approval decision,
  save, select, new session, planning change or installation action is included.

## Test context and evidence

Preserved/isomorphic laws come from G701 test_product_directory.py: current
workspace permission before cursor/decode/UoW, exact digest, bounded scoped
pages, reference/redaction, active list versus revoked detail and missing versus
denied. The new SDK exposure/guidance/profile tests are new-law at this adapter
boundary. The JSON schema exposes the existing product page limit and exact
digest grammar; it does not replace owner validation or narrow other read tools.

Tests use the released SDK client in both selected protocol eras and the actual
HTTP host/read owner over immutable store-return record/page fixtures. Those
fixtures do not implement a store, transaction or pagination state machine;
they prove transport/owner projection composition, not PostgreSQL persistence.
Existing owner tests remain the persistence and directory-query evidence.

At test checkpoint bc2fb843666b5864b4a2ac2b73a5668b03852291, the owning
grandparent source gate reached the intended red:26 support and2 cohort checks
passed;13 standard MCP tests ran in2.272s. Ten original tests passed; the three
new discovery/guidance tests failed for missing tool exposure/status and missing
initialize guidance. Seven assertion failures and two SDK task-group-wrapped
AssertionErrors had those same intended causes, not broken fixture imports.
The gate stopped before later modules; no G4 green is inferred. Cohort source
context absence was verified. Log SHA256
8a11fce3c90625b3dea07d948e7422231adb00c96463c2851762f5dd4080bf7f.

Implementation is prepared; green and default/grandparent cohort validation
remain pending. Tests/assertions are unchanged after intended red. The owning
entrances are the maintained ./test.sh --mcp-source-tests and its existing
--cohort grandparent variant; no alternate runner or ad hoc container is used.

## Security and operational history

Every call still authenticates its current request and uses current workspace
read authorization. Schema validation, owner denial and pagination occur before
store work as required; a denied read does not imply absence. Owner output and
error budgets/redaction remain unchanged, including canary checks for hidden
environment/configuration/material contents. Client approval hints grant no
CPK authority. No route owner, permission, secret, private endpoint, durable
mutation, session/action/run/event, provider capability or network exposure is
introduced. There is no automatic retry, private value intake, publication,
credential change, graph write or installed compatibility claim.

The original [authoring trace](mcp-authoring-discovery-trace.md) is pinned to
accepted0610e945, not retrospectively rewritten as an installed capability.
This source slice adds only the reviewed discovery boundary above.
