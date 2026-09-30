"""JSON command-line interface for OpenAPI inspection operations."""

import argparse
import json
import sys
from typing import Any, Mapping, Sequence

from yaml import YAMLError

from .cli_cache import load_cli_spec_source
from .descriptions import SPEC_GET_SUMMARY, SPEC_INFO_SUMMARY, SPEC_LIST_SUMMARY
from .tools import inspect_spec_get, inspect_spec_info, inspect_spec_list

_GET_SECTIONS = (
    "paths, schemas, parameters, responses, requestBodies, headers, "
    "securitySchemes, links, callbacks, examples"
)


class _HelpFormatter(argparse.HelpFormatter):
    """Wrap prose while preserving line breaks in example commands."""

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        if "\n" in text:
            return "\n".join(indent + line for line in text.splitlines())
        return super()._fill_text(text, width, indent)


class _CommandHelpParser(argparse.ArgumentParser):
    """Render command details together, showing shared arguments only once."""

    command_parsers: Sequence[argparse.ArgumentParser] = ()

    def format_help(self) -> str:
        formatter = self._get_formatter()
        formatter.add_usage(self.usage, self._actions, self._mutually_exclusive_groups)
        formatter.add_text(self.description)

        shared_destinations = {"source", "header", "help"}
        for parser in self.command_parsers:
            positionals = " ".join(
                action.metavar or action.dest
                for action in parser._actions
                if not action.option_strings
            )
            command = parser.prog.removeprefix(f"{self.prog} ")
            formatter.start_section(f"{command} {positionals}")
            formatter.add_text(parser.description)
            formatter.add_arguments(
                action
                for action in parser._actions
                if action.dest not in shared_destinations
            )
            formatter.end_section()

        formatter.start_section("shared arguments and options")
        formatter.add_arguments(
            action
            for action in self.command_parsers[0]._actions
            if action.dest in shared_destinations
        )
        formatter.end_section()
        formatter.add_text(self.epilog)
        return formatter.format_help()


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line parser."""
    parser = _CommandHelpParser(
        prog="openapi-tools-cli",
        formatter_class=_HelpFormatter,
        description=(
            "Inspect local or remote OpenAPI specifications without calling API "
            "operations. Write JSON to stdout; pipe it to jq for formatting. "
            "Start with info, use list to discover names, then get to inspect one item."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, parser_class=argparse.ArgumentParser
    )

    info_parser = subparsers.add_parser(
        "info",
        help=SPEC_INFO_SUMMARY,
        formatter_class=_HelpFormatter,
        description=(
            f"{SPEC_INFO_SUMMARY}. Return an object with openapi (version), "
            "info (title, description, and other API metadata), and servers "
            "(base URLs). Use this first to confirm the spec and its servers."
        ),
        epilog="examples:\n  openapi-tools-cli info ./openapi.yaml | jq",
    )
    _add_source_arguments(info_parser)

    list_parser = subparsers.add_parser(
        "list",
        help=SPEC_LIST_SUMMARY,
        formatter_class=_HelpFormatter,
        description=(
            f"{SPEC_LIST_SUMMARY}. Return a JSON array: paths contains "
            "{path, verbs} objects; other sections contain names. tags lists "
            "tags used by operations. For paths and schemas, glob and tag "
            "filters combine: items must match both. Use the returned names "
            "with get; tags is list-only."
        ),
        epilog=(
            "examples:\n"
            "  openapi-tools-cli list paths ./openapi.yaml --glob '/pet*'\n"
            "  openapi-tools-cli list paths ./openapi.yaml --tag pet --tag admin\n"
            "  openapi-tools-cli list schemas ./openapi.yaml"
        ),
    )
    list_parser.add_argument(
        "section",
        help=f"section to enumerate: {_GET_SECTIONS}, tags (list-only)",
    )
    _add_source_arguments(list_parser)
    list_parser.add_argument(
        "--glob",
        dest="filter_by_glob",
        metavar="PATTERN",
        help=(
            "filter path or item names with shell-style wildcards (*, ?, [abc]); "
            "quote the pattern to prevent shell expansion"
        ),
    )
    list_parser.add_argument(
        "--tag",
        dest="filter_by_tag",
        action="append",
        metavar="TAG",
        help=(
            "filter paths by operation tags or schemas by tags/x-tags; repeat "
            "to match any tag (ignored for other sections)"
        ),
    )

    get_parser = subparsers.add_parser(
        "get",
        help=SPEC_GET_SUMMARY,
        formatter_class=_HelpFormatter,
        description=(
            f"{SPEC_GET_SUMMARY}. Return {{value, line_start, line_end}}. "
            "The line fields are zero-based source positions (null when "
            "unavailable). Resolve local #/... $ref values by default; external "
            "references cannot be resolved."
        ),
        epilog=(
            "examples:\n"
            "  openapi-tools-cli get paths '/pet/{petId}' ./openapi.yaml\n"
            "  openapi-tools-cli get schemas Pet ./openapi.yaml\n"
            "  openapi-tools-cli get schemas Pet ./openapi.yaml --no-resolve-refs"
        ),
    )
    get_parser.add_argument(
        "section", help=f"section containing the item: {_GET_SECTIONS}"
    )
    get_parser.add_argument(
        "name", help="exact path (for example: /pet/{petId}) or component name (Pet)"
    )
    _add_source_arguments(get_parser)
    get_parser.add_argument(
        "--no-resolve-refs",
        dest="resolve_refs",
        action="store_false",
        help="preserve all $ref values, including external references",
    )
    get_parser.set_defaults(resolve_refs=True)
    parser.command_parsers = (info_parser, list_parser, get_parser)
    examples = "\n\n".join(
        command.epilog.removeprefix("examples:\n") for command in parser.command_parsers
    )
    parser.epilog = (
        "examples:\n"
        f"{examples}\n\n"
        "  openapi-tools-cli info https://example.com/openapi.yaml \\\n"
        '    -H "Authorization: Bearer $TOKEN"'
    )
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
