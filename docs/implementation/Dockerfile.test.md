Source: [Dockerfile.test](../../Dockerfile.test).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This test image installs the Servers distribution in /app on the selected Python3.12 slim base and copies repository source, products, fixtures, scripts, documentation and coordination metadata. Its default process is run_all_tests.py, which performs compile/discovery and structural reports. It does not itself grant a Docker socket or start the outer gate's later runtime witnesses.

The base tag and pip-resolved dependency ranges make this an installed test environment, not a complete immutable dependency lock. CPK source pins remain selected by pyproject.toml. Caller-controlled context and image lifecycle belong to test.sh; a successful image build is not completion of the owning gate.

Related source and evidence: [pyproject.toml](../../pyproject.toml), [scripts/run_all_tests.py](../../scripts/run_all_tests.py), [test.sh](../../test.sh).
