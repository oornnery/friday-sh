# TODO — friday

## Configurability

### Providers & Models
- [ ] Dynamic provider registration via `config.toml` (name, base_url, api_key_env, sdk)
- [ ] Allow adding Ollama-compatible endpoints without code changes
- [ ] Per-model settings in config: `temperature`, `max_tokens`, `top_p`, `thinking_budget`
- [ ] Model aliases: `fast`, `smart`, `local` → resolved at runtime

### Modes
- [ ] User-defined modes: load any `.md` file from `~/.config/friday/modes/` as a new mode
- [ ] `AgentMode` becomes an open string instead of a locked enum
- [ ] Mode inheritance: extend a base mode and override only frontmatter fields

### Tools / Skills
- [ ] Plugin system: load tool modules from `~/.config/friday/tools/`
- [ ] Per-mode tool allowlist/denylist in config (complement frontmatter)
- [ ] Tool timeout overrides per tool in config

### Hooks
- [ ] `on_user_input` — pre-process or gate user messages
- [ ] `on_tool_call` — log, audit, or block specific tool calls
- [ ] `on_agent_reply` — post-process or transform replies
- [ ] `on_session_start` / `on_session_end`
- [ ] Hook definition in `config.toml` as shell commands or Python entry points

### Runtime `/setting`
- [ ] Expose all `FridaySettings` fields as mutable via `/setting <key>=<value>`
- [ ] Persist overrides to session envelope so they survive `/session resume`
- [ ] `/setting reset` to restore defaults

---

## Memory

- [ ] Semantic/embedding search (fallback or complement to FTS5 BM25)
- [ ] `friday memory export` / `import` for backup and sharing
- [ ] Memory TTL: auto-expire stale `note` records after N days
- [ ] `/memory pin <id>` and `/memory unpin <id>` from REPL
- [ ] Per-workspace memory isolation option (`scope=repo` strict mode)

---

## CLI / REPL

- [ ] `friday history` command (referenced in ZSH plugin but not implemented)
- [ ] `/undo` — revert last message pair from conversation
- [ ] `/retry` — re-run last user message (useful when model degraded)
- [ ] Multi-line input in REPL (Esc+Enter or `"""` block)
- [ ] `--no-color` / `FRIDAY_NO_COLOR` env flag for piped output
- [ ] `friday version` command that shows model, config path, memory db path
- [ ] Streaming output (token-by-token) for long responses

---

## Agent Runtime

- [ ] Background tasks: fire-and-forget sub-agent with `friday run <task>` and poll via `friday status`
- [ ] Parallel sub-agents: router can dispatch multiple specialists and merge replies
- [ ] Agent retries: configurable retry on tool error before surfacing to user
- [ ] Cost guard: warn or abort if estimated cost exceeds configurable threshold

---

## ZSH Integration

- [ ] `friday history` command: search past sessions from shell
- [ ] `Ctrl+H` keybinding: inline session history search with fzf
- [ ] Auto-completion for `friday ask --mode` and `friday ask --model`
- [ ] Fish shell plugin (`friday.plugin.fish`)

---

## Testing

- [ ] Integration tests for `/session resume` flow end-to-end
- [ ] Test `contains_secret()` against false positive rate with real-world paths
- [ ] Test `safe_path()` with symlinks that escape workspace
- [ ] Test picker scrolling + search state in prompt_toolkit
- [ ] Test MCP server factory with a mock stdio server
- [ ] Coverage for all 5 mode prompts (reader can't write, etc.)

---

## Observability

- [ ] Structured JSON logging mode (`FRIDAY_LOG_FORMAT=json`)
- [ ] Per-session cost report: `friday session cost <id>`
- [ ] Token usage breakdown by tool call in debug mode
- [ ] OpenTelemetry trace export (optional, behind flag)

---

## Distribution

- [ ] Publish to PyPI so `uvx friday` works without git URL
- [ ] `friday update` self-update via `uv tool upgrade friday`
- [ ] Docker image for isolated sandbox mode
- [ ] Homebrew formula
