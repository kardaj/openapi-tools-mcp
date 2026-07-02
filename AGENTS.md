* never use `pip`. Use `uv pip` instead.
* keep `README.md` up to date whenever the server changes.

## Design Philosophy

- MCP tools should be self-describable: generated tool descriptions, parameter schemas, README examples, and tests should tell the same story without requiring users to inspect implementation code.
- Keep the public tool surface small and flexible: prefer extending existing tools and input shapes when that preserves compatibility, and avoid adding narrowly scoped tool names unless a distinct workflow genuinely requires one.

## Quality Gates

- MCP server self-documentation is part of the public API. When a change affects tool behavior, inputs, outputs, caching, errors, or supported sources, the implementation quality gate must inspect generated MCP tool metadata and verify that descriptions and parameter schemas are up to date with the shipped features. Add or update regression tests for generated tool metadata when practical.

<!-- agent-flow:start -->
## Agent Workflow

This section is managed by `agent-flow sync`; do not edit it directly. Add project-specific instructions outside the `agent-flow` markers.

- Before making implementation changes, checking PR state, addressing PR comments, or running PR checks, read and follow `prompts/agent-flow-implement.md`.
<!-- agent-flow:end -->
