"""Actual initializer/owner composition on the owning gate's isolated PostgreSQL."""
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import psycopg
from control_plane_kit_operations.postgres import install_schema
from control_plane_kit_operations.postgres.schema import SchemaInstallationError
from control_plane_kit_operations.workflows import IdempotencyKey
from control_plane_kit_operations.workspace_permissions import (
    WorkspacePermissionCommandService, WorkspacePermissionNotFound, WorkspacePermissionReadService,
)
from receiver_acceptance_operations import IsolatedOperationsSchema, utc_now
from workspace_initialization_fixtures import initialization_inputs, read_progress


def workspace_initialization_acceptance(database_url):
    test = TestCase()
    try:
        fixture, module, plan, index, root, target, intent = initialization_inputs(test)
        policy = intent.authority.administration_policy
        for fault in (None, "schema-ack", "initialization-ack", "receipt-conflict"):
            with IsolatedOperationsSchema(database_url, "cpk_1912_" + uuid4().hex,
                    install_current=fault == "receipt-conflict") as schema:
                commands = WorkspacePermissionCommandService(schema.unit_of_work,
                    administration_policy=policy, clock=utc_now, id_factory=lambda: uuid4().hex)
                reads = WorkspacePermissionReadService(schema.unit_of_work, administration_policy=policy)
                progress = fixture.root / ("progress-" + str(fault))
                connections = []

                def connection(**options):
                    # The component fixture replaces only the actual connection
                    # destination with its existing disposable schema boundary.
                    # Production fixed target validation still runs first.
                    test.assertEqual(options["host"], "127.0.0.1")
                    test.assertEqual(options["port"], 5432)
                    connections.append(options)
                    if (not options["autocommit"] and fault != "receipt-conflict"
                            and "default_transaction_read_only=on" not in options["options"]):
                        test.assertTrue(read_progress(progress)["schema_acknowledged"])
                        # Independent connection sees committed schema before the
                        # initialization UoW can open. No local schema simulator.
                        with schema.connect() as observer:
                            with test.assertRaises(SchemaInstallationError):
                                install_schema(observer, require_empty=True)
                    return psycopg.connect(database_url, autocommit=options["autocommit"],
                        connect_timeout=options["connect_timeout"],
                        options=options["options"].replace("search_path=public", "search_path=" + schema.schema))

                if fault == "receipt-conflict":
                    commands.initialize(intent.installer, idempotency_key=IdempotencyKey("other-command-key"))
                else:
                    real_replace = module.os.replace
                    def replace(source, destination):
                        value = json.loads(Path(source).read_bytes())
                        if ((fault == "schema-ack" and value["schema_acknowledged"])
                                or (fault == "initialization-ack" and value["initialization"] == "matching")):
                            raise OSError("synthetic-private-ack-error")
                        return real_replace(source, destination)
                    with patch.object(module, "connect", side_effect=connection), \
                            patch.object(module.os, "replace", side_effect=replace):
                        if fault is None:
                            result = module.run_workspace_initialization(input_directory=root,
                                progress_directory=progress)
                            test.assertEqual(result["initialization"], "matching")
                            test.assertTrue(result["schema_acknowledged"])
                            test.assertIsNone(result["pending"])
                        else:
                            with test.assertRaises(fixture.api.RootBootstrapError) as caught:
                                module.run_workspace_initialization(input_directory=root,
                                    progress_directory=progress)
                            test.assertNotIn("synthetic-private-ack-error", str(caught.exception))
                            test.assertIsNone(caught.exception.__context__)
                    test.assertTrue(connections[0]["autocommit"])
                    if fault == "schema-ack":
                        test.assertEqual(len(connections), 1)
                        test.assertFalse(read_progress(progress)["schema_acknowledged"])
                        with test.assertRaises(WorkspacePermissionNotFound):
                            reads.installation(intent.installer)
                    else:
                        receipt = reads.installation(intent.installer)
                        test.assertEqual(receipt.actor, intent.installer.identity)
                        test.assertEqual(receipt.idempotency_key, intent.initialization_key.value)
                    # Both acknowledgement failures still left the schema commit
                    # visible; neither is represented as a schema rollback.
                    with schema.connect() as observer:
                        with test.assertRaises(SchemaInstallationError):
                            install_schema(observer, require_empty=True)
                previous = None if not progress.exists() else (progress / "progress.json").read_bytes()
                inspection = fixture.root / ("inspection-" + str(fault))
                with patch.object(module, "connect", side_effect=connection), \
                        patch.object(module, "install_schema", side_effect=AssertionError("inspection installed schema")), \
                        patch.object(WorkspacePermissionCommandService, "initialize",
                            side_effect=AssertionError("inspection initialized policy")):
                    observed = module.run_workspace_initialization(input_directory=root,
                        progress_directory=inspection, inspect_only=True)
                test.assertEqual(observed["initialization"], "missing" if fault == "schema-ack" else
                    "conflict" if fault == "receipt-conflict" else "matching")
                test.assertIn("default_transaction_read_only=on", connections[-1]["options"])
                if previous is not None:
                    test.assertEqual((progress / "progress.json").read_bytes(), previous)
                rendered = json.dumps(observed)
                for private in ("private-initialize-key", "installer-private", "synthetic-private-installer-token"):
                    test.assertNotIn(private, rendered)
        print("workspace initializer: actual PostgreSQL commit, acknowledgement and read-only receipt composition PASS", flush=True)
    finally:
        test.doCleanups()
