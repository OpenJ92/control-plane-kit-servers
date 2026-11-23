Source: [grandparent_sample_admission_qualification.py](../../../scripts/grandparent_sample_admission_qualification.py).
Maintain alongside the named cohort selection.

The original #401 qualification path exposes the product's two public sample
admission tests under their existing class and method names. The cohort runner
can select these same tests by name. Ordinary Docker discovery also runs them
in the [CPK product suite](../products/cpk_server/tests/test_http_sample_admission.py.md).
