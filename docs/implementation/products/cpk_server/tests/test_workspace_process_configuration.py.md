# Dynamic workspace process targets — Servers #341

Unexecuted targets for reviewed plan
https://github.com/OpenJ92/control-plane-kit-servers/issues/341#issuecomment-6462015304.
They enter through the real from_environment/bootstrap composition, retaining
the Operations policy and selection owners. Files and identities are synthetic.

The new workspace policy file must be closed, bounded, regular and redacted.
Policy limits use unique identity/capability values so duplicate rejection cannot
stand in for collection bounds. Catalogue mismatch includes overlapping subset
and superset cases. Actual single/multi credential parsing and _credential_verifier
must accept explicitly empty legacy grants only with valid dynamic policy, retain
the existing fixed full identity, refuse wrong credentials, and preserve static,
missing-grants and invalid/missing-policy refusals. This adds no credential lifecycle.
Managed-health v2 is raw immutable installer input with no selector/UoW placeholder;
the production factory binds the exact real UoW only after its installation receipt
guard. Focused composition substitutes schema/database receipt/provider effects,
but retains the actual effect composition and Operations factory. The existing
isolated-Postgres public fixture remains responsible for real receipt and durable
grant/revoke/restart evidence; these tests do not recreate it.

Mode/schema pairs and catalogue matching are explicit. Existing public installation
artifact helpers stay v1-only and reject v2 on authoring and consumption. A valid
v1 artifact remains supported. Supported bootstrap v2 authoring/trusted-policy
delivery is an unresolved handoff prerequisite, not supplied by these fixtures.

No executable validation has run for these targets. Existing guards may already
pass; missing workspace-policy interpretation or v2 process support should be
reported only where an owning gate actually reaches them. Deeper post-receipt
assertions cannot be credited when parsing stops first. G lifecycle proof remains
mandatory pending. No seed, migration, provider mutation, live deployment or new
installation authority follows from this source/test work.
