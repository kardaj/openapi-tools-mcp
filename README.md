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

TOML version:

```toml
[mcp_servers.openapi-tools]
command = "uvx"
args = ["--from", "git+ssh://git@github.com/kardaj/openapi-tools-mcp.git", "openapi-tools-mcp"]
```

## Available tools

- `spec_info(spec_path)`: Quickly summarize a spec file (OpenAPI version, title/description, servers). Use this first to confirm you're reading the right spec and its base URLs.
- `spec_list(section, spec_path, filter_by_glob?, filter_by_tag?)`: Enumerate keys within a spec section (e.g., all paths, schemas, or responses). Use to discover what exists before drilling into details.
- `spec_get(section, name, spec_path, resolve_refs=True)`: Retrieve a specific item from a section (e.g., one path or schema), with optional `$ref` resolution and source line numbers for precise navigation.

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
