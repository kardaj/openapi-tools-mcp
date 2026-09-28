# OpenAPI Tools MCP and CLI

A [Model Context Protocol](https://spec.modelcontextprotocol.io/) server powered by [fastMCP](https://pypi.org/project/fastmcp/) plus a JSON command-line interface for inspecting local or remote OpenAPI specs. Both interfaces expose the same summary, listing, filtering, retrieval, `$ref` resolution, and source-line behavior.

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

## Use the command-line interface

Run the CLI ephemerally from PyPI with `uvx --from`:

```bash
uvx --from openapi-tools-mcp openapi-tools-cli info ./openapi.yaml | jq
```

For persistent use, install the package as a uv tool and call the dedicated CLI entry point:

```bash
uv tool install openapi-tools-mcp
openapi-tools-cli info ./openapi.yaml
```

The CLI accepts local YAML or JSON paths, including paths with `~` and relative segments, and lowercase `http://` or `https://` URLs:

```bash
openapi-tools-cli info ./openapi.yaml
openapi-tools-cli list paths https://example.com/openapi.yaml
openapi-tools-cli get schemas Pet ~/specs/openapi.json
```

Repeat `-H/--header` for URL request headers. Header names and values are trimmed, values may contain additional colons, and the last identically spelled header name wins. Headers are rejected for local paths:

```bash
openapi-tools-cli info https://example.com/openapi.yaml \
  -H "Authorization: Bearer token" \
  -H "Accept: application/yaml"
```

`list` supports the existing glob filter and match-any tag filter. Each `--tag` occurrence accepts one tag:

```bash
openapi-tools-cli list paths ./openapi.yaml --glob '/pets/*'
openapi-tools-cli list paths ./openapi.yaml --tag pet --tag admin
```

`get` resolves local `$ref` values by default. Preserve references with `--no-resolve-refs`:

```bash
openapi-tools-cli get schemas Pet ./openapi.yaml --no-resolve-refs
```

Successful operations write one newline-terminated JSON value to stdout, so their output can be piped to tools such as `jq`. Expected source, lookup, download, and parse failures write a concise message to stderr and exit with status `1`; command syntax and header usage errors follow argparse conventions and exit with status `2`.

Successful CLI URL downloads are cached for 15 minutes in the platform's conventional per-user cache location. Set `OPENAPI_TOOLS_CACHE_DIR` to use an exact alternative directory, for example `OPENAPI_TOOLS_CACHE_DIR=/private/tmp/.cache/openapi-tools-mcp`; an empty value leaves the platform default unchanged. Entries are shared across CLI processes and isolated by URL plus the complete normalized header mapping; concurrent requests for the same entry coordinate around one download while unrelated entries remain independent. An expired entry is used as stale fallback when refresh fails because of a network error or HTTP 5XX response, while HTTP 4XX and invalid refreshed content still fail. Cache directories and files are restricted to the invoking user, and cache identities contain only cryptographic digests rather than raw header names or values. The downloaded specification body may still contain sensitive API documentation and may persist in this private cache. Cache permission, corruption, or coordination failures, including an unavailable configured directory, degrade to an uncached request without changing a successful command's output. `OPENAPI_TOOLS_CACHE_DIR` affects only the CLI disk cache; the MCP server continues to use its process-local in-memory cache.

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

Downloaded URL content is cached in memory for 15 minutes per MCP server process. Cache entries are keyed by URL plus the complete headers mapping, independent of header insertion order, so different authentication or content-negotiation inputs do not share responses. When an expired cached entry cannot be refreshed because of a network error or HTTP 5XX response, the stale cached content is used for that request. HTTP 4XX responses and unsupported URL schemes surface an error and do not use stale content. The MCP server does not read or write the CLI disk cache.

## License

MIT
