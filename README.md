# OpenAPI Tools MCP Server

A [Model Context Protocol](https://spec.modelcontextprotocol.io/) server powered by [fastMCP](https://pypi.org/project/fastmcp/) for inspecting local OpenAPI specs. It exposes tools for listing and retrieving spec details with optional glob/tag filters and `$ref` resolution.

## Add as an MCP server

Add this server to your MCP client configuration:

```json
{
  "mcpServers": {
    "openapi-tools": {
      "command": "uvx",
      "args": [
        "--from",
        "git+ssh://git@github.com/kardaj/openapi-tools-mcp.git",
        "openapi-tools-mcp"
      ]
    }
  }
}
```

This launches the `openapi-tools-mcp` entrypoint directly from the repository via `uvx`.

## Available tools

- `spec_info(spec_path)`: Returns basic metadata (`openapi`, `info`, `servers`) from the OpenAPI spec at `spec_path`.
- `spec_list(section, spec_path, filter_by_glob?, filter_by_tag?)`: Lists items within `paths`, `tags`, `schemas`, `parameters`, `responses`, `requestBodies`, `headers`, `securitySchemes`, `links`, `callbacks`, or `examples`. Supports glob matching on names and optional tag filtering (for paths/schemas).
- `spec_get(section, name, spec_path, resolve_refs=True)`: Returns a specific item from the same sections as `spec_list`, plus `line_start`/`line_end` (0-based) when possible. Set `resolve_refs=False` to keep `$ref` values intact.

All tools expect a readable OpenAPI YAML/JSON file path on the local filesystem. An example spec lives at `tests/openapi.example.yml`.

## Local development

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
openapi-tools-mcp
```

## License

MIT
