Source: [docker_image_update_images.json](../../../../../products/cpk_server/tests/docker_image_update_images.json).

Fixed #251 inputs: qualified private Gateway/Hello A/Hello B plus the official
public pause 3.10 amd64 manifest. The unchanged peer uses A. Actual image IDs,
platform and configured users are checked before the scenario. Hello/Gateway
configure named users whose nonroot UIDs were proved in the accepted #191 gate;
pause config is 65535:65535 with /pause. Normal jobs preload this tuple using the
existing Actions package-read login; optional manual qualification inputs cannot
replace it. No publication, credential delivery or cache-presence assumption.

Workflow preloading validates the fixed and optional manual sets before pulling,
deduplicates their bounded union, and compares each fixed image ID with this
reviewed record. Normal source-built artifact checks remain in the gate.
