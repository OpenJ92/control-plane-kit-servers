Source: [cpk_server_published_image_smoke.sh](../../../scripts/cpk_server_published_image_smoke.sh).
Maintain with published-baseline evidence selection.

The existing canonical published image is still pulled and checked with its
historical inputs. Explicit CPK_SERVER_SMOKE_PROFILE=published-baseline separates
it from required wrapped-source fixture evidence. It neither disables the new
source receiver nor proves that the old image contains SDK health. Catalogue,
image digest and bootstrap publication remain unchanged by Servers200.
