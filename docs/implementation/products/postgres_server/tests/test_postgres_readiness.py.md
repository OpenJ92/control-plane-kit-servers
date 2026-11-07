Source: [test_postgres_readiness.py](../../../../../products/postgres_server/tests/test_postgres_readiness.py).

The existing password-file, bounded subprocess and state tests retain ownership.
The fixed psql environment requires SCRAM via PGREQUIREAUTH, so providing a
password alone cannot make a no-challenge listener count as authenticated SQL.
The owning source-image witness still must qualify the shipping fresh recipe.
#2089 includes a synthetic byte-equivalence counterexample: the product file
reader strips trailing LF while the original SQL credential value preserves it.
This is explicitly unsupported for a future original-check fulfillment unless
its delivery proof establishes exact equivalence. No password hashes or real
credentials are emitted and no generic credential parser is changed.
