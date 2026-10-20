# Managed entrypoint boundary

Source: [entrypoint.py](../../../../../../products/cloudflared_connector/src/control_plane_kit_servers_cloudflared_connector/entrypoint.py).

Servers #284 begins with an importable `main() -> int` scaffold raising
`NotImplementedError`. This is deliberately missing behavior, not an implemented
launch path. Module execution forwards its future result to `SystemExit`.
The scaffold permits the existing Docker package suite to collect the focused
targets without treating a missing import as causal red.

The reviewed future boundary loads the existing SDK configuration, validates
the managed product surface and token path, and invokes the existing coordinator
once on the main thread. Native custody, signals, cleanup and exit mapping remain
coordinator-owned. No behavior has been validated at this checkpoint.
