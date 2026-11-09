Source: [http_sample_image_preflight.sh](../../../scripts/http_sample_image_preflight.sh).
The new full image input enters the shared Core decoder BEFORE ordinary root
build or registration network/PG work. One exact cached controller, network none,
read-only source/Core mounts, no socket/pull/build; pinned Core054 export and
private scratch cleanup. That isolated validation-controller start is an explicit
effect, distinct from downstream registration. Invalid input stops with its exit
code; it does not silently repair prerequisites. See
[source action and evidence limits](../../qualified-child-image-inputs.md).
Owning source gate63645d0 passed the pure/ordinary-launcher refusal tests. The
launcher uses external Docker/Git transport doubles there; no real registration
preflight/runtime or image qualification is claimed by that source result.
