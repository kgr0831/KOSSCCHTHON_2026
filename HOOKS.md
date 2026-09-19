# Hook policy

No hooks are enabled by default.

Hooks execute commands automatically, so add one only for a mechanical check that cannot be expressed in `AGENTS.md` or normal validation. Keep it repository-scoped, review its exact command before trusting it, and make it fail safely.

Good first hooks are narrow: block a known destructive command pattern, format one generated file, or record a required validation result. Do not use hooks to inject secrets, start background services, or make network calls.
