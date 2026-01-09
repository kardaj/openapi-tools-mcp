"""MCP server exposing utilities for inspecting local OpenAPI specs."""

from pathlib import Path
from typing import Any, Dict, Iterable

from fastmcp import FastMCP

from .tools import (
    load_spec,
    spec_get as spec_get_impl,
    spec_info as spec_info_impl,
    spec_list as spec_list_impl,
)


mcp = FastMCP("openapi-tools")


def _resolve_spec_path(spec_path: str) -> Path:
    return Path(spec_path).expanduser().resolve()


@mcp.tool()
def spec_info(spec_path: str) -> Dict[str, Any]:
    """Quickly summarize a spec file (OpenAPI version, title/description, servers). Use this first to confirm you're reading the right spec and its base URLs."""
    path = _resolve_spec_path(spec_path)
    loaded = load_spec(path)
    return spec_info_impl(loaded["spec"])


@mcp.tool()
def spec_list(
    section: str,
    spec_path: str,
    filter_by_glob: str | None = None,
    filter_by_tag: str | Iterable[str] | None = None,
) -> Any:
    """Enumerate keys within a spec section (e.g., all paths, schemas, or responses). Use to discover what exists before drilling into details."""
    path = _resolve_spec_path(spec_path)
    loaded = load_spec(path)
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
    spec_path: str,
    resolve_refs: bool = True,
) -> Any:
    """Retrieve a specific item from a section (e.g., one path or schema), with optional $ref resolution and source line numbers for precise navigation."""
    path = _resolve_spec_path(spec_path)
    loaded = load_spec(path)
    return spec_get_impl(
        loaded["spec"], section, name, spec_path=path, resolve_refs=resolve_refs
    )


def main() -> None:
    """Entrypoint used by the console script."""
    mcp.run()


if __name__ == "__main__":
    main()
