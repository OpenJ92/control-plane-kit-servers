# `client/workflow.py`

`TopologyClient.plan` keeps its existing file and saved-revision paths and adds
`AuthoredDesiredGraph`. The authored path reads workspace fences, requests exact
receiver context, reads only required public verifier families, performs the pure
pre-wire transform, canonicalizes the complete graph, persists it, journals the
request, and only then dispatches.

Prepared retry rereads the original file solely to compare path, byte size, and
SHA-256. The outgoing graph comes only from the immutable preparation artifact,
which must also decode and re-encode to identical canonical Core graph bytes.
Identity factories, context reads, verifier reads, and route composition are
never invoked on replay.
