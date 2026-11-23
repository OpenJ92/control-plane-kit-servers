# Gateway self-health diagnostic

After bootstrap, use the [public topology client](../products/cpk_server/docs/client.md)
to plan topology changes, apply an approved plan, and inspect its status.

The #221 diagnostic uses signed credentials to request the gateway's own
readiness and checks for a matching healthy result. A successful public gateway probe alone leaves
that question open. [Public acceptance #342](https://github.com/OpenJ92/control-plane-kit-servers/issues/342)
tracks the replacement proof required before [#340](https://github.com/OpenJ92/control-plane-kit-servers/issues/340)
can retire the diagnostic and its callers.

The [historical #221 recipe](learning/gateway-self-health-diagnostic-221.md)
preserves the original commands, approval requirements, and unverified live
prerequisites.
