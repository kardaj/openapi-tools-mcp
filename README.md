# OpenAPI Tools MCP Server

A minimal [Model Context Protocol](https://spec.modelcontextprotocol.io/) server powered by [fastMCP](https://pypi.org/project/fastmcp/). It exposes a couple of starter tools (`ping` and `echo`) and is ready for expansion with OpenAPI-aware functionality.

## Install with `uvx`

Install directly from the repository and launch the server via the published console script:

```bash
uvx --from git+https://github.com/your-org/openapi-tools-mcp openapi-tools-mcp
```

Replace the repository URL with the actual location of this repo. `uvx` will resolve the `openapi-tools-mcp` entrypoint defined in `pyproject.toml` and start the MCP server.

## Local development

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
openapi-tools-mcp
```

The server currently exposes two tools:

- `ping`: returns `pong` for quick health checks.
- `echo`: returns whatever message is provided.

Use this skeleton to add OpenAPI tooling as MCP tools or resources.
