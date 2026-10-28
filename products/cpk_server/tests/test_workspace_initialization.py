"""Protected initializer commands and controller refusal at their own boundary."""
import contextlib
import importlib
import io
import json
import unittest
from unittest.mock import patch

from workspace_initialization_fixtures import initialization_inputs


class WorkspaceInitializationTests(unittest.TestCase):
    def inputs(self):
        try:
            return initialization_inputs(self)
        except ModuleNotFoundError as error:
            if error.name == "control_plane_kit_servers_cpk_server.bootstrap_initialization":
                self.fail("supported workspace initializer is absent")
            raise

    def test_private_helper_rechecks_real_administrator_before_database_access(self):
        fixture, module, plan, index, root, target, intent = self.inputs()
        fixture.private_write(root / "credential", b"synthetic-nonadministrator-canary")
        with patch.object(module, "connect") as connection:
            with self.assertRaises(fixture.api.RootBootstrapError) as caught:
                module.run_workspace_initialization(input_directory=root,
                    progress_directory=fixture.root / "progress")
        connection.assert_not_called()
        self.assertNotIn("synthetic-nonadministrator-canary", str(caught.exception))
        self.assertIsNone(caught.exception.__context__)
        self.assertFalse((fixture.root / "progress").exists())

    def test_helper_refuses_mismatched_target_package_or_private_intent_without_io(self):
        fixture, module, plan, index, root, target, intent = self.inputs()
        cases = [("database", "unapproved-database"), ("namespace", "unapproved-schema"),
            ("driver_image_id", "sha256:" + "d" * 64), ("schema_sha256", "e" * 64),
            ("operations_commit", "f" * 40), ("data_volumes", []), ("labels", {})]
        for field, value in cases:
            with self.subTest(field=field):
                fixture.private_write(root / "acquisition.json", fixture.api.canonical({**target, field: value}))
                with patch.object(module, "connect") as connection:
                    with self.assertRaises(fixture.api.RootBootstrapError):
                        module.run_workspace_initialization(input_directory=root,
                            progress_directory=fixture.root / "progress")
                connection.assert_not_called()
        fixture.private_write(root / "acquisition.json", fixture.api.canonical(target))
        private = json.loads((root / "workspace-intent.json").read_bytes())
        private["initialization_idempotency_key"] = "substituted-private-key"
        fixture.private_write(root / "workspace-intent.json", fixture.api.canonical(private))
        with patch.object(module, "connect") as connection:
            with self.assertRaises(fixture.api.RootBootstrapError):
                module.run_workspace_initialization(input_directory=root,
                    progress_directory=fixture.root / "progress")
        connection.assert_not_called()

    def test_connection_failure_retains_only_bounded_intent_and_fixed_error(self):
        fixture, module, plan, index, root, target, intent = self.inputs()
        progress = fixture.root / "progress"
        with patch.object(module, "connect", side_effect=OSError("private-password-canary")) as connection:
            with self.assertRaises(fixture.api.RootBootstrapError) as caught:
                module.run_workspace_initialization(input_directory=root, progress_directory=progress)
        self.assertEqual(connection.call_count, 1)
        options = connection.call_args.kwargs
        self.assertEqual((options["host"], options["port"], options["dbname"], options["user"]),
            ("127.0.0.1", 5432, target["database"], target["username"]))
        self.assertIs(options["autocommit"], True)
        observed = json.loads((progress / "progress.json").read_bytes())
        self.assertEqual(observed["pending"], "schema")
        self.assertFalse(observed["schema_acknowledged"])
        self.assertEqual(observed["initialization"], "unknown")
        rendered = json.dumps(observed) + str(caught.exception)
        for value in ("private-password-canary", "private-initialize-key", "installer-private",
                "synthetic-private-installer-token", "synthetic-unused-material"):
            self.assertNotIn(value, rendered)
        self.assertIsNone(caught.exception.__context__)

    def test_cli_has_fixed_helper_inputs_and_rejects_database_override(self):
        _, module, *_ = self.inputs()
        cli = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_cli")
        for command in ("initialize-workspace", "inspect-workspace-initialization"):
            with patch("sys.argv", ["bootstrap", command]), \
                    patch.object(module, "run_workspace_initialization", return_value={"status": "fixture"}) as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 0)
            run.assert_called_once_with(inspect_only=command == "inspect-workspace-initialization")
            with self.subTest(command=command), patch("sys.argv", ["bootstrap", command,
                    "--database-url", "unapproved"]), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    cli.main()
                self.assertEqual(caught.exception.code, 2)

    def test_inspection_refuses_existing_writer_lock_before_receipt_or_provider_access(self):
        fixture, module, plan, index, root, target, intent = self.inputs()
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        inspector = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_initialization_runtime")
        state = fixture.root / "state"
        with runtime._locked(state), patch("docker.DockerClient") as provider:
            with self.assertRaises(fixture.api.RootBootstrapError):
                inspector.inspect_initialization(plan, index, state)
        provider.assert_not_called()
        self.assertFalse((state / "receipt.json").exists())

    def test_unresolved_inspection_preserves_original_history_and_never_redispatches(self):
        fixture, module, plan, index, root, target, intent = self.inputs()
        inspector = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_initialization_runtime")
        state = fixture.root / "state"
        state.mkdir(mode=0o700)
        receipt = {"schema": "cpk.root-bootstrap.receipt.v1", "plan_digest": plan["digest"],
            "driver_image_id": plan["driver_image_id"], "phase": "acquiring",
            "pending": "initialize-workspace", "observations": {"initialization": {"schema_acknowledged": True}},
            "initialization_inspection": {"pending": "create-helper", "helper_id": None,
                "temporary_volumes": {}, "observation": {"initialization": "matching"}, "cleanup": "not-started"}}
        fixture.private_write(state / "receipt.json", fixture.api.canonical(receipt))
        before = (state / "receipt.json").read_bytes()
        with patch("docker.DockerClient") as provider:
            with self.assertRaises(fixture.api.RootBootstrapError):
                inspector.inspect_initialization(plan, index, state)
        provider.assert_not_called()
        self.assertEqual((state / "receipt.json").read_bytes(), before)
