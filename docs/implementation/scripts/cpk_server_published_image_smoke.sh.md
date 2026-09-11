Source: [scripts/cpk_server_published_image_smoke.sh](../../../scripts/cpk_server_published_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This wrapper takes an explicit CPK_SERVER_IMAGE or derives a default digest
reference from the local generic CPK descriptor using host Python. It disables
the delegated image build, pulls that reference and invokes image_smoke from
the repository working directory.

There is no opt-in or plan-only branch, and an explicit override need not be a
digest. This file neither checks the shared coordinate manifest nor attests
source/image equivalence. Process, database, request and cleanup evidence comes
from the image smoke; the final echo means that command returned success.

Related source: [generic descriptor](../products/cpk_server/product.cpk.json.md),
[image smoke](../../../scripts/cpk_server_image_smoke.sh).
