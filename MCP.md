# MCP policy

MCP servers are optional integrations, not part of the default harness.

- Add a server only when a task needs its live data or actions.
- Prefer read-only tools. Configure write tools to require approval.
- Store tokens in the operating system or service credential flow; never commit them to `config.toml`.
- Keep each server project-scoped unless it is useful and trusted across unrelated projects.
- Verify a server with `codex mcp list` after adding it, then complete OAuth locally when required.

Examples are deliberately omitted: a generic harness should not install services or authorize accounts by default.
