"""JSON command-line interface for OpenAPI inspection operations."""

import argparse
import json
import sys
from typing import Any, Mapping, Sequence

from yaml import YAMLError

from .cli_cache import load_cli_spec_source
from .descriptions import SPEC_GET_SUMMARY, SPEC_INFO_SUMMARY, SPEC_LIST_SUMMARY
from .tools import inspect_spec_get, inspect_spec_info, inspect_spec_list


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line parser."""
    parser = argparse.ArgumentParser(
        prog="openapi-tools-cli",
        description="Inspect local or remote OpenAPI specifications and emit JSON.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser(
        "info",
        help=SPEC_INFO_SUMMARY,
        description=(
            f"{SPEC_INFO_SUMMARY}. URL downloads use a private 15-minute disk cache."
        ),
    )
    _add_source_arguments(info_parser)

    list_parser = subparsers.add_parser(
        "list",
        help=SPEC_LIST_SUMMARY,
        description=(
            f"{SPEC_LIST_SUMMARY}. URL downloads use a private 15-minute disk cache."
        ),
    )
    list_parser.add_argument(
        "section",
        help="section to enumerate (for example: paths, schemas, or tags)",
    )
    _add_source_arguments(list_parser)
    list_parser.add_argument(
        "--glob",
        dest="filter_by_glob",
        metavar="PATTERN",
        help="filter names with the existing glob matching behavior",
    )
    list_parser.add_argument(
        "--tag",
        dest="filter_by_tag",
        action="append",
        metavar="TAG",
        help="match this tag; repeat the option to match any of several tags",
    )

    get_parser = subparsers.add_parser(
        "get",
        help=SPEC_GET_SUMMARY,
        description=(
            f"{SPEC_GET_SUMMARY}. URL downloads use a private 15-minute disk cache."
        ),
    )
    get_parser.add_argument("section", help="section containing the item")
    get_parser.add_argument("name", help="item name within the section")
    _add_source_arguments(get_parser)
    get_parser.add_argument(
        "--no-resolve-refs",
        dest="resolve_refs",
        action="store_false",
        help="preserve local $ref values instead of resolving them",
    )
    get_parser.set_defaults(resolve_refs=True)
    return parser


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source",
        help=(
            "local YAML/JSON path or a lowercase http:// or https:// URL; local "
            "paths expand ~ and resolve absolutely"
        ),
    )
    parser.add_argument(
        "-H",
        "--header",
        action="append",
        default=[],
        metavar="NAME: VALUE",
        help="URL request header; repeat for multiple headers (URLs only)",
    )


def _parse_headers(
    raw_headers: Sequence[str], parser: argparse.ArgumentParser
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_header in raw_headers:
        if ":" not in raw_header:
            parser.error(f"invalid header {raw_header!r}: expected 'Name: value'")
        name, value = raw_header.split(":", 1)
        name = name.strip()
        if not name:
            parser.error(f"invalid header {raw_header!r}: header name cannot be empty")
        headers[name] = value.strip()
    return headers


def _parse_source(
    source: str,
    raw_headers: Sequence[str],
    parser: argparse.ArgumentParser,
) -> str | Mapping[str, Any]:
    is_url = source.startswith(("http://", "https://"))
    if raw_headers and not is_url:
        parser.error("-H/--header can only be used with an http:// or https:// source")
    headers = _parse_headers(raw_headers, parser)
    if is_url:
        return {"url": source, "headers": headers}
    return source


def _run_operation(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Any:
    source = _parse_source(args.source, args.header, parser)
    if args.command == "info":
        return inspect_spec_info(source, source_loader=load_cli_spec_source)
    if args.command == "list":
        return inspect_spec_list(
            args.section,
            source,
            filter_by_glob=args.filter_by_glob,
            filter_by_tag=args.filter_by_tag,
            source_loader=load_cli_spec_source,
        )
    return inspect_spec_get(
        args.section,
        args.name,
        source,
        resolve_refs=args.resolve_refs,
        source_loader=load_cli_spec_source,
    )


def _error_message(exc: BaseException) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _run_operation(args, parser)
    except (KeyError, OSError, UnicodeError, ValueError, YAMLError) as exc:
        print(_error_message(exc), file=sys.stderr)
        return 1
    serialized = json.dumps(result)
    sys.stdout.write(f"{serialized}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
