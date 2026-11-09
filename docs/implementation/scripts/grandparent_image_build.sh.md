Source: [grandparent_image_build.sh](../../../scripts/grandparent_image_build.sh).

The [grandparent artifact packet](../../grandparent-image.md) owns exact sources,
commands, index permissions and limits. The owning root selector exports selected
Git objects, builds a distinct product-based image and verifies installed content
using that finished image without a source mount. It retains the candidate and
public provenance, cleans only its own context/helper, and reports listening
startup as unobserved. It does not bootstrap a sibling or generate credentials.
