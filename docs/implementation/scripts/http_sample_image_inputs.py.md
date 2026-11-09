Source: [http_sample_image_inputs.py](../../../scripts/http_sample_image_inputs.py).
Shared Core-only decoder for [the #163 full image input](../../qualified-child-image-inputs.md).
The six-role mapping and original Core OCI codec are the sole selection rules.
Recursive object-pair decoding rejects ambiguous role/descriptor keys only for
the new full JSON. Legacy PG parsing remains unchanged. The CLI performs no
fixture, provider or graph work and emits a fixed error, without candidate text.
Owning source gate63645d0 passed28 support+8 pure/launcher tests; see
[the scoped receipt](../../qualified-child-image-inputs.md). No image qualification.
