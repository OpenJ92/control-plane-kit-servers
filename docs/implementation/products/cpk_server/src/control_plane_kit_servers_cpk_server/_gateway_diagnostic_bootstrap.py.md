Source: [_gateway_diagnostic_bootstrap.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/_gateway_diagnostic_bootstrap.py).
Maintain this companion with its source and selected contracts.

Run-only loader reads independently trusted, readonly-mounted operator setup.
Files are absolute, regular, bounded and opened no-follow/nonblocking; protected
files must belong to root/current UID and exclude group/other permissions. Parent
directory integrity and authorization of the selected mount remain invocation
requirements; these checks do not make arbitrary caller files trustworthy.

The existing static-development verifier consumes only trusted principal bindings.
This explicitly local diagnostic authentication is not production identity.
A protected existing DSN composes PostgresUnitOfWork directly without schema
installation. Existing Secrets bootstrap registry/resolver consumes protected
routing; no keys, credentials or registrations are created. Approval is reopened
on each check so file replacement can withdraw it. There is no atomic revocation
claim across subsequent provider/network effects; current provider policy still
applies. Private values never enter structured output or exception evidence.
