Source: [authentication.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py).

Existing credential extraction and static verifiers are unchanged. #315 adds
ConfiguredPrincipalAuthorizer, which accepts only exact credential-free Core
principal values and snapshots normalized grants into an immutable mapping.
Full issuer/subject/kind is the identity key. Equal policies collapse; any
conflict permanently denies that identity in this snapshot, including disjoint
workspaces or a later repeated entry. Missing identity/workspace denies.

Every authorize call consults the independent configured policy, intersects it
with the original request's workspace scopes and constructs a same-identity
target-workspace context. It does not mutate the request, union grants, retain
credentials or choose by credential order. Empty intersections carry no powers;
Operations enforces required scopes. Construction supplies no dynamic reload
surface: restart/replacement is required. Representation omits the policy map.
