# Bootstrap image publication — Servers158

Two images were published sequentially with explicit user approval. Both workflow
runs checked out Servers `4468cd06e9754304fb1e02bba752eb1fd11d7c9f`, whose full tree
matches accepted roadmap merge `a229bc8ce992312f52119ef65a5b621f0c7e6af2`. The source
includes the reviewed Docker-backed publication preflight; no host Python check
was used. The common new tag is `bootstrap-158-4468cd0`.

| Product | Immutable digest | Source and configuration |
| --- | --- | --- |
| CPK (all three variants) | `sha256:336f536d72e2bff7e1c9d19e86c795f935176f6a6f5de878504fb2d948f978ab` | Servers `4468cd0`; user10001; `python -m control_plane_kit_servers_cpk_server.server` |
| Secrets | `sha256:41aba38eb255779c8a0230724d9cc4fffd1dc5d5dfbfafdc133f1629139edfe7` | Secrets `68d0da6aed3a383d6bdc284cf4a6a6063a31487e`; packaging Servers `4468cd0`; user10006; `cpk-secrets-entrypoint` |

[CPK publication](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/34291699723)
completed and its GHCR digest, immutable pull, numeric user, command and
Linux/amd64 configuration were verified before the
[Secrets publication](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/34291903144)
was dispatched. Secrets passed the same checks, including its expected entrypoint
and the build log's accepted custody-source pin. Each workflow was dispatched
once; no old tag was overwritten. Publication does not claim multi-platform
support beyond the observed Linux/amd64 artifacts.

Secrets descriptor provenance intentionally identifies its package repository
commit68d0da6, while this record separately identifies the Servers Dockerfile/build
commit4468cd0. The CPK variants share one published artifact. PostgreSQL,
cloudflared and other products were not republished or repinned.

The owning test gate retains source-built numeric protected-file witnesses and
published Secrets smoke, and now runs the existing CPK published-image smoke with
the canonical immutable coordinate explicitly supplied. This avoids that wrapper's
host-Python default lookup. Generated coordinate/catalogue consistency remains
checked by the existing Docker preflight.

Security and operations: registry publication used GitHub Actions package-write
authority, never runtime control or custody secrets. No retained installation,
database, DNS, ingress, child deployment or credential was changed. Old registry
versions remain available. A coordinate rollback requires a reviewed revert and
does not automatically alter running systems. Executable root bootstrap remains
Servers156; these images establish its truthful artifact prerequisite.
