# Friday v2

## Status

Implemented on 9 April 2026.

Friday v2 modernizes the runtime around `pydantic-ai 1.78`, unifies the CLI and REPL command surface, and removes the old mixed naming scheme.

## What Changed

### Unified command grammar

- Top-level verbs remain:
  - `friday ask`
  - `friday chat`
- Resource commands are now plural and consistent:
  - `friday models`
  - `friday modes`
  - `friday sessions`
  - `friday settings`
- Default resource action is `list`
- Legacy commands such as `config`, `model`, `mode`, and `session` are rejected with a suggestion to use the new command

### Unified runtime

- One runtime path now powers both `ask` and `chat`
- `create_agent()` builds mode-specific agents
- `execute_agent()` drives runs to completion, including deferred approvals
- `instructions` replace the previous static prompt assembly
- `UsageLimits(tool_calls_limit=max_steps, request_limit=max_steps + 5)` are applied on every run
- delegated specialist runs share `ctx.usage`

### Structured internal contracts

- Final internal output is `AgentReply`
- Runtime output is `TurnOutput = AgentReply | DeferredToolRequests`
- Router delegation returns validated `AgentReply` objects from specialist agents
- prompt frontmatter is validated through `ModePromptConfig`

### History, memory, and persistence

- history trimming is now pair-safe by cutting only at user-turn boundaries
- `WorkingMemory` is deterministic and rendered into runtime instructions
- sessions are versioned with `SessionEnvelope(schema_version=2)`
- session persistence uses validated `ModelMessage` serialization

### Tools, approvals, and MCP

- domain toolsets are built with `FunctionToolset`
- sensitive domains are wrapped with `ApprovalRequiredToolset`
- `approval_policy` now drives deferred approval behavior:
  - `ask`
  - `auto`
  - `never`
- configured MCP servers are attached directly as toolsets
- MCP servers receive stable `id` and `tool_prefix` values based on configured names

### REPL alignment

- REPL commands now mirror the CLI:
  - `/models`
  - `/modes`
  - `/sessions`
  - `/settings`
- `/models set` and `/modes set` mutate only the current chat session
- `/settings` is read-only in the REPL
- `/clear` starts a fresh session without changing the current model or mode

### Shell integration

- the ZSH plugin now uses `friday sessions list --plain`
- `Ctrl+G` is tied to sessions instead of the removed `friday history`
- session switching follows the same shape as model switching via `sessions set [id]`
- shell completions match the v2 command surface

## Quality Gates

The v2 implementation is expected to stay green on:

```bash
./.venv/bin/ruff check src tests
./.venv/bin/ty check --exclude 'tests/'
./.venv/bin/pytest -q
```

## Test Coverage Added

- default resource actions for `models`, `sessions`, and `settings`
- legacy command rejection with suggestions
- REPL `/models set` and `/modes set` preserving current history
- non-interactive picker failure paths
- deferred approval flow for `auto` and `never`
- usage limit wiring from mode config
- MCP toolset wiring
- pair-safe history reduction
- run stats aggregation for both independent and shared `RunUsage`

## Notes

- `settings` remains read-only in this round
- no observability or tracing was added
- no LLM-based summarization was added
- `docs/plan-v1.md` remains as historical context only
