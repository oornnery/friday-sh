# Friday

Friday is an LLM-powered shell agent for coding, debugging, reading code, and writing docs from the terminal.

It uses `pydantic-ai 1.78`, a unified runtime for `ask` and `chat`, structured agent replies, deferred tool approvals, bounded history, persisted sessions, and optional MCP toolsets.

## Quick Start

```bash
uv sync
cp .env.example .env

# one-shot
friday ask "what does this project do?"

# repl
friday chat
```

## Requirements

- Python 3.13+
- `uv`
- At least one provider configured: Anthropic, OpenAI, Mistral, Z.AI, or Ollama

## Install

```bash
git clone <repo-url> friday
cd friday
uv sync
```

To expose the CLI:

```bash
uv tool install -e .
```

Or add the local venv to your path:

```bash
export PATH="$PWD/.venv/bin:$PATH"
```

## Command Surface

Friday v2 keeps verbs for interaction and uses plural resource commands everywhere else.

### Ask

```bash
friday ask "review this project"
friday ask --mode debug "why is this test failing?"
friday ask --model openai:gpt-4.1 "summarize this repo"
git diff | friday ask "review these changes"
```

### Chat

```bash
friday chat
friday chat --mode code
friday chat --model mistral:devstral-latest
```

### Models

```bash
friday models
friday models list
friday models list openai
friday models set anthropic:claude-sonnet-4-20250514
```

`friday models` defaults to `list`. `friday models set` opens an interactive picker when no model is provided and the terminal is interactive.

### Modes

```bash
friday modes
friday modes list
friday modes set auto
friday modes set debug
```

### Sessions

```bash
friday sessions
friday sessions list
friday sessions set <session-id>
friday sessions delete <session-id>
friday sessions new
```

### Memories

```bash
friday memories
friday memories list
friday memories search "Fabio"
friday memories set "Show model, tokens, and cost at the end"
friday memories get <memory-id>
friday memories delete <memory-id>
```

### Settings

```bash
friday settings
friday settings list
friday settings get default_model
```

## REPL Commands

The REPL uses the same grammar as the CLI:

| Command | Description |
| --- | --- |
| `/help` | Show commands |
| `/debug [on|off|status]` | Toggle verbose logging and full stack traces |
| `/models [list]` | List models |
| `/models set [model]` | Change the current chat model |
| `/modes [list]` | List modes |
| `/modes set [mode]` | Change the current chat mode |
| `/sessions [list]` | List sessions |
| `/sessions set [id]` | Switch to a saved session |
| `/sessions new` | Start a new session |
| `/sessions delete [id]` | Delete a saved session |
| `/memories [list]` | List shared memories visible to the current repo |
| `/memories search <query>` | Search shared memory and indexed chat snippets |
| `/memories set <text>` | Save a pinned shared memory |
| `/memories get [id]` | Show one shared memory |
| `/memories delete [id]` | Delete one shared memory |
| `/settings [list]` | Show effective settings for the current chat |
| `/settings get <key>` | Show one setting |
| `/clear` | Reset conversation and start a new session |
| `/quit` | Exit |
| `/exit` | Exit |

Legacy names such as `/model`, `/mode`, `/session`, `friday config`, and `friday model` are intentionally rejected with a suggestion to use the new command.

## Response Footer

Every visible response ends with a compact footer:

```text
model: anthropic:claude-sonnet-4-20250514  tokens: 123 total, 88 in, 35 out  cost: n/d
```

When the provider exposes billing metadata, `cost` is shown. Otherwise Friday prints `n/d`.

## Configuration

Friday reads configuration in this order:

1. `FRIDAY_*` environment variables
2. `.env`
3. `~/.config/friday/config.toml` or `friday.toml`

### Example `.env`

```bash
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
MISTRAL_API_KEY=...
ZAI_API_KEY=...
ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
```

### Example `config.toml`

```toml
default_model = "zai:glm-5-turbo"
fallback_model = "mistral:devstral-latest"
default_mode = "auto"
approval_policy = "ask"
max_steps = 25

[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
```

### Main Settings

| Setting | Default |
| --- | --- |
| `default_model` | `zai:glm-5-turbo` |
| `fallback_model` | `mistral:devstral-latest` |
| `default_mode` | `auto` |
| `approval_policy` | `ask` |
| `max_steps` | `25` |
| `session_dir` | `~/.local/share/friday/sessions` |
| `config_dir` | `~/.config/friday` |
| `memory_db_path` | `~/.config/friday/memory.db` |
| `memory_top_k` | `6` |
| `memory_auto_promote` | `true` |

## Agent Runtime

Friday now has one runtime path for both CLI and REPL:

- `AgentReply` is the internal structured final output
- `TurnOutput = AgentReply | DeferredToolRequests`
- `instructions` are rebuilt every run from mode prompts plus deterministic working memory
- shared long-term memory lives in `SQLite + FTS5`, separate from session JSON
- top-level turns can retrieve relevant snippets from explicit memories and older chats
- `WorkingMemory` is reset on `/clear`, `/sessions new`, and `/sessions set`
- `UsageLimits` are applied on every run
- delegated subagents share `ctx.usage`
- session history is reduced by user-turn boundary so tool call / tool return chains stay intact

### Modes

| Mode | Purpose |
| --- | --- |
| `auto` | Router mode that can delegate to specialist agents |
| `code` | Edit, refactor, and verify code |
| `reader` | Read and explain code |
| `write` | Generate docs and prose |
| `debug` | Diagnose failures and runtime issues |

Mode prompts live in `src/friday/agent/prompts/*.md` and are parsed through a validated `ModePromptConfig`.

## Approvals

Sensitive tool domains use deferred approvals:

- `ask`: asks in the terminal and resumes the run
- `auto`: approves automatically
- `never`: denies automatically

Friday uses `ApprovalRequiredToolset` for sensitive toolsets and converts decisions into `DeferredToolResults` before resuming the run.

## MCP

`mcp_servers` are wired directly into the agent as toolsets. Both `stdio` and `http` transports are supported.

Each configured server gets a stable `id` and `tool_prefix` based on its configured name, which keeps MCP tools discoverable and avoids collisions.

## Providers

| Prefix | Provider |
| --- | --- |
| `anthropic:` | Anthropic |
| `openai:` | OpenAI |
| `mistral:` | Mistral |
| `zai:` | Z.AI |
| `ollama:` | Ollama |

## ZSH Plugin

Source `src/friday/shell/friday.plugin.zsh` from your `.zshrc`.

It provides:

- `f "question"` as shorthand for `friday ask`
- `Ctrl+F` to ask about the current buffer or last command
- `Ctrl+G` to fuzzy-pick a saved session and prepare `friday sessions set ...`
- `friday-select-model` for `fzf`-based model selection
- shell completions aligned with the v3 command surface

## Development

```bash
uv sync
./.venv/bin/ruff check src tests
./.venv/bin/ty check --exclude 'tests/'
./.venv/bin/pytest -q
```
