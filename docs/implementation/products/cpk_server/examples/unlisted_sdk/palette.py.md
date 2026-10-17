Source: [palette.py](../../../../../../products/cpk_server/examples/unlisted_sdk/palette.py).

Independent standard-library HTTP application used by the maintained #237 source
composition. It imports the SDK host, not Hello or controller implementation.
SDK setup reads the delivered common configuration file and provides baseline
lifecycle health without an application callback. Ordinary business paths differ
between the two examples. The listener is loopback-only with an OS-assigned port;
logs omit requests and credentials. The witness owns process termination/restart.
No image publication, dependency readiness or production lifecycle claim follows.

S1 #249 reads ordinary application JSON from `PALETTE_CONFIGURATION_FILE` once at
startup, bounds its shape/size and serves the selected colors at `/palette`.
The example still supplies no identity or health callbacks: the SDK owns those.
Replacing the process is required to observe new application content. The owning
witness checks a changed business value against delivered bytes while preserving
the separate wrapper file and configured receiver identity.
