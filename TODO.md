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

### Approval & Allowed Commands

- [ ] `allowed_commands` list in `config.toml` — commands matching these patterns auto-approve without prompt (e.g. `ls`, `git status`, `pytest`)
- [ ] `blocked_commands` list — always deny these patterns regardless of policy
- [ ] Glob/regex matching for allowed/blocked patterns (e.g. `git *`, `npm test`)
- [ ] Per-mode approval overrides (e.g. reader mode always `never`, code mode `ask`)

### Hooks

- [ ] `on_user_input` — pre-process or gate user messages
- [ ] `on_tool_call` — log, audit, or block specific tool calls
- [ ] `on_agent_reply` — post-process or transform replies
- [ ] `on_session_start` / `on_session_end`
- [ ] Hook definition in `config.toml` as shell commands or Python entry points

### Plugin system
- [ ] Load custom tools from `~/.config/friday/tools/` as Python modules
- [ ] Each plugin defines one or more tools with metadata (name, description, args)
- [ ] Plugins can specify which modes they are allowed in
- [ ] Example: a `git` plugin that provides `git_status`, `git_diff`, etc. tools that are only allowed in `shell` and `code` modes

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
- [ ] `Ctrl+I` keybinding — opens a Textual inline `TextArea` for composing multi-line prompts with syntax highlighting, then sends on submit
- [ ] `--no-color` / `FRIDAY_NO_COLOR` env flag for piped output
- [ ] `friday version` command that shows model, config path, memory db path
- [ ] Streaming output (token-by-token) for long responses
- [ ] Smart paste/content collapse: when user pastes or pipes large text, display `[paste: 2.1KB]` in the conversation instead of the full content. The full text is still sent to the LLM. Configurable threshold (e.g. `collapse_threshold=500` chars). Same for tool output display — long `run_shell` results show a collapsed summary in the chat with option to expand

---

## Agent Runtime

### Multi-step orchestration (priority)

- [ ] Router re-delegation loop: after a specialist returns, the router can inspect the result and re-delegate to another specialist (e.g. reader → code → debug) forming a workflow chain
- [ ] Max delegation depth configurable via `max_delegation_depth` setting (default 3)
- [ ] Each specialist result feeds back to the router with accumulated context, so the router can decide: respond to user, or delegate again
- [ ] Parallel sub-agents: router can dispatch multiple specialists concurrently and merge replies
- [ ] Specialist can signal "I need shell access" or "I need write access" in its reply, triggering the router to escalate to a capable agent

### Other

- [ ] Background tasks: fire-and-forget sub-agent with `friday run <task>` and poll via `friday status`
- [ ] Agent retries: configurable retry on tool error before surfacing to user
- [ ] Cost guard: warn or abort if estimated cost exceeds configurable threshold

---

## ZSH Integration

### Daemon mode (priority)

- [ ] `friday daemon` — long-running background process that keeps the agent runtime warm (model connections, memory db, config loaded). Eliminates cold-start latency on each `f` invocation
- [ ] `f` / `friday ask` communicate with the daemon via unix socket or named pipe instead of spawning a new process
- [ ] Daemon auto-starts on shell init (`source friday.plugin.zsh`) and auto-stops on shell exit
- [ ] Fallback: if daemon is not running, `f` falls back to direct `friday ask` (current behavior)

### Shell command injection

- [ ] Agent shell tool sends commands to the **user's active shell session** instead of running in a subprocess — command appears in shell history and inherits the shell environment
- [ ] Auto-confirm setting: `shell_inject_auto_confirm` (bool, default `false`) — when `true`, commands are sent to the shell without the Yes/No picker
- [ ] Configurable via `/setting shell_inject_auto_confirm=true` and `config.toml`
- [ ] Uses ZSH `zle` buffer injection (`BUFFER="cmd"; zle accept-line`) or `print -z "cmd"` to push commands to the shell input stack

### Last command output capture

- [ ] Capture stdout/stderr of the last command automatically via `preexec`/`precmd` hooks using `script` or `tee` into a temp file (e.g. `/tmp/friday-lastcmd-$$.out`)
- [ ] `Ctrl+F` and `f` can read the captured output and send it as context to the agent — not just the command name and exit code
- [ ] `FRIDAY_LAST_OUTPUT` env var or temp file path available to the agent via `WorkspaceContext`
- [ ] Configurable: `capture_last_output` (bool, default `true`) — disable if performance impact is noticeable
- [ ] Max capture size (e.g. 8KB) to avoid sending huge outputs to the LLM
- [ ] Privacy: never capture output from commands matching `FRIDAY_CAPTURE_EXCLUDE` patterns (e.g. `ssh`, `pass`, `gpg`)

### RPROMPT status

- [ ] Show Friday status in ZSH right prompt: `[friday:auto(glm-5-turbo)]`
- [ ] Updates dynamically via `precmd` hook when mode/model changes
- [ ] Reads current mode/model from daemon state or `friday setting show` cache

### Other

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

- [X] Publish to PyPI so `uvx friday` works without git URL
- [ ] `friday update` self-update via `uv tool upgrade friday`
- [ ] Docker image for isolated sandbox mode
- [ ] Homebrew formula
