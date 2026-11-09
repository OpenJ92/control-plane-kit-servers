Source: [gateway_packaged_owner.sh](../../../scripts/gateway_packaged_owner.sh).
Maintain with the one #163 gateway image action; sourcing declares functions only.

Closed roles, attempted cid/name records, fresh reservation owner, local optionless
volume checks and internal-network identity constrain creation/cleanup. Each
mutation rechecks the daemon. Unknown same-label objects are never removed;
read/removal/absence failures remain failed, with no second allocation/retry.
The signer wait accepts only observed exited0 and never restarts its lifetime.
This is test resource ownership, not provider/application durable semantics.
