"""Bind a supplied owner on a fresh PostgreSQL namespace, before serving requests."""
import psycopg

from control_plane_kit_operations.postgres import PostgresUnitOfWork, install_schema
from control_plane_kit_operations.postgres.current_schema_verification import namespace_is_object_free
from control_plane_kit_operations.postgres.schema import SchemaInstallationError
from control_plane_kit_operations.workflows import IdempotencyKey
from control_plane_kit_operations.workspace_permissions import (
    WorkspaceAdministrationContext,
    WorkspacePermissionCommandService,
    WorkspacePermissionInitializationReceipt,
    WorkspacePermissionReadService,
)


def install_or_verify_owner(database_url, policy, *, clock, id_factory):
    owner, = policy.administrators
    context = WorkspaceAdministrationContext(owner, policy.installation_id)
    # Scoped by the durable installation and actor. Rotating a bearer is independent.
    key = IdempotencyKey("configured-installation-owner-v1")
    connection = psycopg.connect(database_url)
    try:
        # This read starts the outer transaction. The fresh-only schema installer
        # consequently uses a savepoint and keeps its namespace lock until commit.
        if namespace_is_object_free(connection):
            try:
                install_schema(connection, require_empty=True)
            except SchemaInstallationError:
                # A concurrent first start may have won the namespace lock.
                # Only an existing, fully verified binding may now be served.
                if namespace_is_object_free(connection):
                    raise
            else:
                commands = WorkspacePermissionCommandService(
                    lambda: PostgresUnitOfWork(lambda: connection),
                    administration_policy=policy, clock=clock, id_factory=id_factory)
                commands.initialize(context, idempotency_key=key)
                return

        install_schema(connection)
        reader = WorkspacePermissionReadService(
            lambda: PostgresUnitOfWork(lambda: connection), administration_policy=policy)
        receipt = reader.installation(context)
        if type(receipt) is not WorkspacePermissionInitializationReceipt or receipt.actor != owner:
            raise ValueError("configured installation owner differs from existing binding")
    finally:
        connection.close()
