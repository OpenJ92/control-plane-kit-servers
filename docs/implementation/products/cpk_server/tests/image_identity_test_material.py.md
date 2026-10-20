Source: [image_identity_test_material.py](../../../../../products/cpk_server/tests/image_identity_test_material.py).

Closed #191 target data for the existing five fixed artifacts. It reads unchanged
fixture coordinates and original raw manifest sidecars, constructs finite Engine
and Interpreter observations, and offers config-valued and manifest-valued forms.
This constructs test inputs only; it does not decide qualification, infer a store,
contact Docker or grant artifact/runtime acceptance.

The future qualifier is imported inside `qualified_images` only when a focused
target invokes it. Root early-red material and package collection need no new
implementation. This permits an honest admission regression before the new
propagation interface exists. `qualified_images` will produce real qualified
immutable sets for the placement targets, preserving all original ownership laws.
