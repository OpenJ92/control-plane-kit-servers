Source: [test_docker_image_update_provider.py](../../../../../products/cpk_server/tests/test_docker_image_update_provider.py).

The owning Docker package suite starts the existing private Secrets fixture
process to check its generated endpoint/bootstrap mapping and connector intent.
The existing custodian writes a random synthetic connector token through public
HTTP; its real receipt is used by the synthetic ingress allocation. The existing
resolver must read the value, and teardown revocation must make resolution denied.
Teardown with a different provider registration is refused while the allocation
and resolvable token remain intact.
No private store is read. The database URL is parsed configuration only; this
focused fixture does not connect to PostgreSQL or Docker or call Cloudflare.

A negative test checks that a failed custody write admits no allocation and a
foreign workspace grant causes no custody call. These are fixture-composition
tests; owner suites retain the secret protocol/lifecycle laws. Process stop and
temporary-directory cleanup use existing context managers. All execution remains
inside the maintained Docker-backed ./test.sh, before the long runtime scenario.
