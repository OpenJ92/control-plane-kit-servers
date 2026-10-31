# Pinned cloudflared notice inputs

Source: [cloudflared-manifest.json](../../../../../products/cloudflared_connector/licenses/cloudflared-manifest.json).

The103 path/blob pairs come from the complete, nontruncated Git tree for upstream
source commit `81a53555aa827fca88605d7e67ad5c03cda468d2`, resolved from tag2026.6.1.
The set includes root LICENSE and vendored files whose basename is LICENSE,
NOTICE, COPYING or PATENTS, including dotted extensions. Root LICENSE has Git
blob `7a4a3ea2424c09fbe48d455aed1eaa94d9124835` (Apache-2.0 text).
The input records source provenance; it does not rebuild or attest the copied
native binary. The distinct native image digest remains separately pinned.

Build collection requires the source archive's full notice set to equal this
manifest and verifies every Git blob identity. It preserves relative paths and
the exact manifest bytes in the image. Packaged targets independently check
each expected bundled notice blob against this committed input.

These are factual packaging inputs, not an assertion that every upstream or
downstream legal obligation is settled. SDK/Servers root license declarations
were absent in the inspected inputs; image publication remains separate.
No collection or image-target execution has occurred at this checkpoint.
