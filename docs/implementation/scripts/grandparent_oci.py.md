Source: [grandparent_oci.py](../../../scripts/grandparent_oci.py).

The [grandparent packet](../../grandparent-image.md) owns this bounded local-base
transport. Read-only cached-image export is capped; this socket-free controller
validates only a safe OCI layout preserving the original approved root digest,
referenced blob bytes/sizes and selected platform/config. It writes only fresh
owned scratch, reports no Env, and refuses optimized Python before touching it.
BuildKit receives the validated layout by named context, never by registry fallback.
Owning tests cover exact content, substitution, platform, wrong root and optimization.
