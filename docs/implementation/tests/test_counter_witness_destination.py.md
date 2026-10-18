Source: [test_counter_witness_destination.py](../../../tests/test_counter_witness_destination.py).

The owning Docker-backed suite invokes the actual pure shell helper. Positive
cases prove the sole destination and boundary prefix lengths; negative cases
cover owner/package overrides, production tags, invalid characters and shell
syntax passed as data. Refusal requires nonzero status and empty output. Tests
do not mock Docker/GitHub or claim workflow interpolation and provider access
are validated by this lower-level helper.
