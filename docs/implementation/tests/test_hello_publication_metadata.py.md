Please update alongside [test_hello_publication_metadata.py](../../../tests/test_hello_publication_metadata.py).

Normal Docker-owned package tests exercise the pure response validator and its
real command entrypoint, plus the actual pure shell destination guard. Independent
owner and package overrides, wrong tags and malformed source commits must refuse
without emitting a destination, before the publisher may perform any provider or
Docker operation. Laws cover unused source tags across pages, exact private
package identity and repository association, malformed/duplicate pages and tags,
one exact post-push tag/digest association, full source commit syntax, and missing
or corrupt files producing refusal without output. No fake gh/Docker executable,
network call, upload, deletion or external visibility claim is involved.
