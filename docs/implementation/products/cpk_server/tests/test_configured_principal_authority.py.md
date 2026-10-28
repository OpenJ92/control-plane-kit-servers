Source: [test_configured_principal_authority.py](../../../../../products/cpk_server/tests/test_configured_principal_authority.py).

#315 target tests for the approved restart-configured permission source. Policy
lookup uses full identity/workspace and intersects the original request ceiling.
Equal normalized policies collapse; conflicts deny permanently within that
directory, including disjoint workspaces and later duplicate entries. Separate
directories demonstrate process replacement, not hot reload. Startup tests use
real configuration/verifier/create_app with only effectful application construction
and the listener replaced. Injecting a verifier alone does not supply authority.

The initial test-only checkpoint preceded implementation. Run 40009978175 showed
the intended missing-interface/forwarding assertions; downstream policy laws were
not executed by that red run. The implementation now supplies the interfaces;
full owning green remains pending, and laws earn evidence only when executed.
Normal Docker-backed ./test.sh/PR CI is required; no host or alternate harness.
All tokens and identities are synthetic. No confidential provision is enabled.

For #341, the effectful factory replacement returns a real static
CpkServerOperationsApplication over the existing recording services instead of a
namespace/mock carrying only a service map. The host now preserves that configured
application. Existing credential, receiving, forwarding and no-effect assertions
are unchanged. Validation is pending the owning Docker gate.
