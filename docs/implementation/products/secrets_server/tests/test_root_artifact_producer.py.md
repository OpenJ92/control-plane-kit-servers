Source: [test_root_artifact_producer.py](../../../../../products/secrets_server/tests/test_root_artifact_producer.py).

#191 targets invoke the actual publication shell with synthetic Git/Docker
observations inside the owning Docker unit image. Both existing root product
branches must reject dirty source, build Linux/amd64 with exact source revision,
validate observed user/platform/revision before push, report actual execution ID
and repository digest, and retain failure if identity drifts after the one push.
No retry or input-image deletion can mask that ambiguous publication.

Stubs record commands rather than exercising a real registry. This is producer
control-flow coverage, not publication permission or evidence that an artifact
exists. The later exact source/tag/private destination packet remains mandatory.
