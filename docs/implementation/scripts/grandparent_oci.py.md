Source: [grandparent_oci.py](../../../scripts/grandparent_oci.py).

The [grandparent packet](../../grandparent-image.md) owns this bounded local-base
transport. Read-only cached-image export is capped; this socket-free controller
validates only a safe OCI layout preserving the original approved root digest,
referenced blob bytes/sizes and selected platform/config. It writes only fresh
owned scratch, reports no Env, and refuses optimized Python before touching it.
BuildKit receives the validated layout by named context, never by registry fallback.
Owning tests cover exact content, substitution, platform, wrong root and optimization.

The explicit controller profile requires the immutable cached controller ID,
root user, empty entrypoint and its test command. The shared Python API accepts
an exact expected entrypoint while preserving the empty default; callers cannot
silently treat a provider, controller and CPK runtime as interchangeable bases.
