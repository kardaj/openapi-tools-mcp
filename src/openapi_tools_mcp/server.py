"""MCP server exposing utilities for inspecting local or remote OpenAPI specs."""

from typing import Any, Dict, Iterable

from fastmcp import FastMCP

from .tools import (
    load_spec_source,
)
from .tools import (
    spec_get as spec_get_impl,
)
from .tools import (
    spec_info as spec_info_impl,
)
from .tools import (
    spec_list as spec_list_impl,
)

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


@mcp.tool()
def spec_info(spec_path: SpecPath) -> Dict[str, Any]:
    """Quickly summarize an OpenAPI spec from a local path string or URL source object. For remote specs, pass {"url": "https://example.com/openapi.yaml", "headers": {"Header-Name": "value"}}; headers are optional, only http/https URLs are supported, and successful downloads are cached in memory for 15 minutes with stale fallback on network errors or HTTP 5XX refresh failures."""
    loaded = load_spec_source(spec_path)
    return spec_info_impl(loaded["spec"])


@mcp.tool()
def spec_list(
    section: str,
    spec_path: SpecPath,
    filter_by_glob: str | None = None,
    filter_by_tag: str | Iterable[str] | None = None,
) -> Any:
    """Enumerate keys within a spec section from a local path string or URL source object. For remote specs, pass spec_path as {"url": "https://example.com/openapi.yaml", "headers": {"Header-Name": "value"}}; headers are optional, only http/https URLs are supported, and successful downloads are cached in memory for 15 minutes with stale fallback on network errors or HTTP 5XX refresh failures."""
    loaded = load_spec_source(spec_path)
    return spec_list_impl(
        loaded["spec"],
        section,
        filter_by_glob=filter_by_glob,
        filter_by_tag=filter_by_tag,
    )


@mcp.tool()
def spec_get(
    section: str,
    name: str,
    spec_path: SpecPath,
    resolve_refs: bool = True,
) -> Any:
    """Retrieve a specific item from a local path string or URL source object, with optional $ref resolution and source line numbers. For remote specs, pass spec_path as {"url": "https://example.com/openapi.yaml", "headers": {"Header-Name": "value"}}; headers are optional, only http/https URLs are supported, and successful downloads are cached in memory for 15 minutes with stale fallback on network errors or HTTP 5XX refresh failures."""
    loaded = load_spec_source(spec_path)
    return spec_get_impl(
        loaded["spec"],
        section,
        name,
        spec_path=loaded.get("source_path"),
        source_text=loaded.get("source_text"),
        resolve_refs=resolve_refs,
    )


def main() -> None:
    """Entrypoint used by the console script."""
    mcp.run()


if __name__ == "__main__":
    main()
