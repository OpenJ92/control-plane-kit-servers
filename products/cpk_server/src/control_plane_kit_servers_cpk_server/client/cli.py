"""Thin ordinary-host command line for the public topology client."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .journal import JournalError
from .profile import ClientConfigurationError, load_profile
from .transport import ClientAuthorizationError, ClientTransportError
from .workflow import ClientInputError, ClientResult, TopologyClient


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        profile = load_profile(arguments.profile)
        client = TopologyClient(profile)
        if arguments.command == "plan":
            if arguments.resume is not None:
                result = client.resume_prepare(arguments.resume)
            elif arguments.desired_graph is not None:
                result = client.plan(arguments.desired_graph, title=arguments.title)
            else:
                raise ClientInputError("desired graph or operation resume is required")
        elif arguments.command == "apply":
            result = client.apply(
                arguments.operation_ref,
                execute_plan=arguments.execute_plan,
                approve_plan=arguments.approve_plan,
                approve_destructive_plan=arguments.approve_destructive_plan,
            )
        elif arguments.command == "status":
            result = client.status(arguments.operation_ref)
        else:
            raise ClientInputError("client command is unsupported")
    except ClientAuthorizationError as error:
        _error(str(error), json_output=arguments.json)
        return 3
    except ClientInputError as error:
        _error(str(error), json_output=arguments.json)
        return 2
    except (ClientConfigurationError, JournalError, ClientTransportError) as error:
        _error(str(error), json_output=arguments.json)
        return 5
    _render(result, json_output=arguments.json)
    return result.exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cpk")
    parser.add_argument("--profile", required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan")
    source = plan.add_mutually_exclusive_group(required=True)
    source.add_argument("desired_graph", nargs="?", type=Path)
    source.add_argument("--resume", metavar="OPERATION_REF")
    plan.add_argument("--title", default="Topology deployment")
    plan.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    apply = commands.add_parser("apply")
    apply.add_argument("operation_ref")
    apply.add_argument("--execute-plan", required=True, metavar="PLAN_ID")
    approval = apply.add_mutually_exclusive_group()
    approval.add_argument("--approve-plan", metavar="PLAN_ID")
    approval.add_argument("--approve-destructive-plan", metavar="PLAN_ID")
    apply.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    status = commands.add_parser("status")
    status.add_argument("operation_ref")
    status.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    return parser


def _render(result: ClientResult, *, json_output: bool) -> None:
    value = result.descriptor()
    if json_output:
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return
    print(f"status: {result.status}")
    print(f"operation: {result.operation_ref}")
    if result.plan_id is not None:
        print(f"plan: {result.plan_id}")
    if result.run_id is not None:
        print(f"run: {result.run_id}")
    print(f"execution: {result.execution}")
    print(f"advancement: {result.advancement}")
    if result.required_scope is not None:
        print(f"required authorization: {result.required_scope}")
    if result.destructive is not None:
        print(f"destructive: {'yes' if result.destructive else 'no'}")
    for change in result.changes:
        print(
            "change: "
            + " ".join(
                str(change[name])
                for name in ("operation", "target")
                if name in change
            )
        )
    if result.next_public_read is not None:
        print(f"next public read: {result.next_public_read}")


def _error(message: str, *, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps(
                {"schema": "cpk.client-error.v1", "status": "error", "message": message},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
    else:
        print(f"cpk: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
