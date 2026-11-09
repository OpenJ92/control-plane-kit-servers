Source: [test_child_bootstrap_fixture.py](../../../../../products/secrets_server/tests/test_child_bootstrap_fixture.py).
Maintain with the exclusive synthetic Secrets bootstrap helper.

Inside the owning Docker tests, prove prepopulated custody refuses without any
seed overwrite, fresh files have protected modes/owners, and reinitialization is
refused. Only temporary synthetic data is used. Native Docker volume identity,
provider custody/restart and cleanup belong to the reviewed image action.
