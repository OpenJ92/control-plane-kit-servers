Source: [test_postgres_startup.py](../../../../../products/postgres_server/tests/test_postgres_startup.py).

Product-owned startup targets exercise the current child's executable/socket
metadata association, descriptor and executable rechecks, fixed IPv4 endpoint,
bounded FD enumeration and cumulative TCP reads, unavailable metadata, and
cancellation. The filesystem fixtures are metadata evidence tests; they do not
establish actual container permissions, native lock ownership or live recovery.

Coordinator and main tests cover no aggregate initialization deadline,
management creation only after admission, stop/native-exit precedence,
observation failure and late management-bind failure, and synchronous bounded
native reap before any startup cleanup worker. Existing authentication, SQL
readiness and post-start concurrent shutdown laws remain in their owning tests.
The lifecycle test fixture supplies valid product control configuration because
that admission must remain before native spawn even when host binding is delayed.
