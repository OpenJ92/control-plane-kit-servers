Source: [counter.py](../../../../../../products/cpk_server/examples/unlisted_sdk/counter.py).

Independent standard-library HTTP application used by the maintained #237 source
composition. It imports the SDK host, not Hello or controller implementation.
SDK setup reads the delivered common configuration file and provides baseline
lifecycle health without an application callback. Ordinary business paths differ
between the two examples. The listener is loopback-only with an OS-assigned port;
logs omit requests and credentials. The witness owns process termination/restart.
No image publication, dependency readiness or production lifecycle claim follows.
