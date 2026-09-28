"""MCP server exposing utilities for inspecting local or remote OpenAPI specs."""

from typing import Any, Dict, Iterable

from fastmcp import FastMCP

from .descriptions import (
    SPEC_GET_DESCRIPTION,
    SPEC_INFO_DESCRIPTION,
    SPEC_LIST_DESCRIPTION,
)
from .tools import inspect_spec_get, inspect_spec_info, inspect_spec_list

SpecPath = str | Dict[str, Any]

mcp = FastMCP(
    name="openapi-tools",
    instructions=(
        "Use this server when you need to read openapi*.yml/openapi*.yaml (or "
        "OpenAPI JSON) files and extract paths/tags/components without loading the "
        "whole spec. List first, then fetch one item; resolve local-only #/... $ref; "
        "return YAML line ranges. Read local files or HTTP(S) URL sources with "
        "optional headers; successful URL downloads are cached for 15 minutes."
    ),
    website_url="https://github.com/kardaj/openapi-tools-mcp",
)


@mcp.tool(description=SPEC_INFO_DESCRIPTION)
def spec_info(spec_path: SpecPath) -> Dict[str, Any]:
    return inspect_spec_info(spec_path)


@mcp.tool(description=SPEC_LIST_DESCRIPTION)
def spec_list(
    section: str,
    spec_path: SpecPath,
    filter_by_glob: str | None = None,
    filter_by_tag: str | Iterable[str] | None = None,
) -> Any:
    return inspect_spec_list(
        section,
        spec_path,
        filter_by_glob=filter_by_glob,
        filter_by_tag=filter_by_tag,
    )


@mcp.tool(description=SPEC_GET_DESCRIPTION)
def spec_get(
    section: str,
    name: str,
    spec_path: SpecPath,
    resolve_refs: bool = True,
) -> Any:
    return inspect_spec_get(
        section,
        name,
        spec_path,
        resolve_refs=resolve_refs,
    )


def main() -> None:
    """Entrypoint used by the console script."""
    mcp.run()


if __name__ == "__main__":
    main()
