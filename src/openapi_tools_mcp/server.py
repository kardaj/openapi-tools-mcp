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
    """Inspect spec metadata at `spec_path` (YAML/JSON); returns openapi version, `info`, and `servers`."""
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
    """List names in a section of the spec at `spec_path`; supports paths, schemas, parameters, responses, tags, requestBodies, headers, securitySchemes, links, callbacks, examples."""
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
    """Fetch `name` from a section (paths, schemas, parameters, responses, requestBodies, headers, securitySchemes, links, callbacks, examples) of the spec at `spec_path`; returns the value plus optional `line_start`/`line_end` (0-based) from the source file. Set `resolve_refs` to False to keep $ref values in responses."""
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
