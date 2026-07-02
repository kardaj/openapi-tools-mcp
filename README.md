# OpenAPI Tools MCP Server

A [Model Context Protocol](https://spec.modelcontextprotocol.io/) server powered by [fastMCP](https://pypi.org/project/fastmcp/) for inspecting local or remote OpenAPI specs. It exposes tools for listing and retrieving spec details with optional glob/tag filters and `$ref` resolution.

The server also publishes MCP metadata (`instructions` and `website_url`) to guide clients toward local-file OpenAPI inspection workflows.

## Add as an MCP server

Add this server to your MCP client configuration (PyPI):

```json
{
  "mcpServers": {
    "openapi-tools": {
      "command": "uvx",
      "args": [
        "--from",
        "openapi-tools-mcp",
        "openapi-tools-mcp"
      ]
    }
  }
}
```

This launches the `openapi-tools-mcp` entrypoint from PyPI via `uvx`.

TOML version (PyPI):

```toml
[mcp_servers.openapi-tools]
command = "uvx"
args = ["--from", "openapi-tools-mcp", "openapi-tools-mcp"]
```

You can also install directly from GitHub with `uvx`:

```bash
uvx --from git+ssh://git@github.com/kardaj/openapi-tools-mcp.git openapi-tools-mcp
```

## Available tools

- `spec_info(spec_path)`: Quickly summarize a spec source (OpenAPI version, title/description, servers). Use this first to confirm you're reading the right spec and its base URLs.
- `spec_list(section, spec_path, filter_by_glob?, filter_by_tag?)`: Enumerate keys within a spec section (e.g., all paths, schemas, or responses). Use to discover what exists before drilling into details.
- `spec_get(section, name, spec_path, resolve_refs=True)`: Retrieve a specific item from a section (e.g., one path or schema), with optional `$ref` resolution and source line numbers for precise navigation.

All tools accept either a readable OpenAPI YAML/JSON file path on the local filesystem or a URL source object. Local paths keep the existing behavior, including `~` expansion and absolute path resolution. An example spec lives at `tests/openapi.example.yml`.

URL source objects are passed through the existing `spec_path` argument:

```json
{
  "url": "https://example.com/openapi.yaml",
  "headers": {
    "Authorization": "Bearer token",
    "Accept": "application/yaml"
  }
}
```

The `headers` object is optional and defaults to no extra request headers. Only `http://` and `https://` URLs are supported. Remote YAML and JSON documents are both supported.

Downloaded URL content is cached in memory for 15 minutes per server process. Cache entries are keyed by URL plus the complete headers mapping, independent of header insertion order, so different authentication or content-negotiation inputs do not share responses. When an expired cached entry cannot be refreshed because of a network error or HTTP 5XX response, the stale cached content is used for that request. HTTP 4XX responses and unsupported URL schemes surface an error and do not use stale content.

## License

MIT
