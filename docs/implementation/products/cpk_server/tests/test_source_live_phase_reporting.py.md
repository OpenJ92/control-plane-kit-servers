Source: [products/cpk_server/tests/test_source_live_phase_reporting.py](../../../../../products/cpk_server/tests/test_source_live_phase_reporting.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

Three in-memory tests check the emitted schema/selected evidence, rejection of
four unsafe identifier examples, ordered failure/skipped/cleanup records, and
retention of primary plus cleanup error codes. Call recording proves the
supplied cleanup callback executes once after the selected action failure.

The StringIO sink and no-op/failing callbacks do not exercise durable storage,
provider absence, ledger I/O failure, BaseException handling or concurrent
publication. The tests do not establish all possible redaction cases or the
security of forged evidence objects. A recorded removed stage is callback
outcome reporting, not an independent resource query.

Related source: [phase reporter](../../../scripts/cpk_server_source_live_report.py.md).
