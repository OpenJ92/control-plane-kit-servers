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
from .workflow import ClientInputError, ClientResult, TopologyClient, _unique_object


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        profile = load_profile(arguments.profile)
        client = TopologyClient(profile)
        if arguments.command == "overview":
            result = client.overview()
        elif arguments.command == "draft":
            if arguments.draft_command == "list":
                result = client.draft_list(limit=arguments.limit, cursor=arguments.cursor)
            elif arguments.draft_command == "show":
                result = client.draft_show(arguments.draft_id, arguments.revision)
            elif arguments.draft_command == "save":
                result = client.draft_save(arguments.graph, title=arguments.title)
            elif arguments.draft_command == "revise":
                result = client.draft_revise(arguments.draft_id, arguments.graph, arguments.expected_head)
            elif arguments.draft_command == "select":
                result = client.draft_select(arguments.draft_id, arguments.revision)
            else:
                result = client.draft_resume(arguments.operation_ref)
        elif arguments.command == "plan":
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
    overview = commands.add_parser("overview")
    overview.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    draft = commands.add_parser("draft")
    catalogue = draft.add_subparsers(dest="draft_command", required=True)
    for name in ("list", "show", "save", "revise", "select", "resume"):
        command = catalogue.add_parser(name)
        command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
        if name in {"show", "revise", "select"}:
            command.add_argument("draft_id")
        if name in {"show", "select"}:
            command.add_argument("--revision", required=True, type=_catalogue_integer)
        if name in {"save", "revise"}:
            command.add_argument("graph", type=Path)
        if name == "save":
            command.add_argument("--title")
        if name == "revise":
            command.add_argument("--expected-head", required=True, type=_catalogue_integer)
        if name == "resume":
            command.add_argument("operation_ref")
        if name == "list":
            command.add_argument("--limit", default=50, type=_catalogue_integer)
            command.add_argument("--cursor", type=_catalogue_cursor)
    return parser


def _catalogue_integer(value):
    if not value.isascii() or not value.isdigit() or value.startswith("0") or len(value) > 19:
        raise argparse.ArgumentTypeError("expected a canonical positive integer")
    number = int(value)
    if number > 2**63 - 1:
        raise argparse.ArgumentTypeError("integer exceeds the public bound")
    return number


def _invalid_json_constant(value):
    raise ValueError("nonstandard JSON constant")


def _catalogue_cursor(value):
    try:
        if len(value.encode()) > 16384:
            raise ValueError
        result = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_invalid_json_constant)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, RecursionError):
        raise argparse.ArgumentTypeError("cursor must be a bounded JSON object") from None


def _render(result: ClientResult, *, json_output: bool) -> None:
    value = result.descriptor()
    if json_output:
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return
    if value.get("schema", "").startswith("cpk.client-catalogue-"):
        print(json.dumps(value, sort_keys=True, indent=2))
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
