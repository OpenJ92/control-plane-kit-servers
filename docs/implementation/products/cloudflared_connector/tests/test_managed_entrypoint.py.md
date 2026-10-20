# Managed entrypoint targets

Source: [test_managed_entrypoint.py](../../../../../products/cloudflared_connector/tests/test_managed_entrypoint.py).

Governing issue: [Servers #284](https://github.com/OpenJ92/control-plane-kit-servers/issues/284),
with Meridian and Kepler PLAN PASS and Rowan's reconciled qualification decision.
All targets are new laws at the process-entry boundary, preserving the accepted
SDK and coordinator ownership.

Nine test methods cover real configuration delivery, exact one-call handoff on
the main thread, coordinator result preservation, missing/malformed/mode-invalid
or symlink configuration, wrong product surface, missing/empty/relative token
path, bounded loader exceptions, inert import and module-exit forwarding.
The fixture uses the already accepted product authority generator and actual
Core codec; no fixture bytes or authority material are printed.

Valid delivery uses a real 0444 file and wraps the actual selected SDK loader.
Only the effect-owning coordinator is mocked. A deliberately absent token file
proves this entrypoint does not require reading native-owned token bytes.
Invalid delivery must not invoke that effect owner. Loader failure must not
expose candidate paths, token sentinels or exception details. These tests do not
duplicate native spawn/health/signal state machines.

Current source is an importable `NotImplementedError` scaffold. Expected causal
red is missing `main()` behavior after successful policy, compile and collection.
Do not credit a fixture exception, bad codec field, import failure or Docker
apparatus error as red. No tests have been run at this checkpoint.

Run only the established Docker `./test.sh` after exact-target review and resource
coordination. Existing automatic product discovery includes this file; no
collection configuration or skip changes are needed. The ordinary fail-fast
suite should stop at the connector targets, before later image effects.

This focused entrypoint evidence does not qualify an OCI image, real PID1,
native offline management interval, daemon stop grace or cleanup. Those remain
explicit packaged witness targets before image implementation/acceptance.
