# friday

[![PyPI](https://img.shields.io/pypi/v/friday-sh?logo=pypi&label=PyPI)](https://pypi.org/project/friday-sh/)
[![Python](https://img.shields.io/pypi/pyversions/friday-sh?logo=python&label=Python)](https://pypi.org/project/friday-sh/)
[![CI](https://img.shields.io/github/actions/workflow/status/oornnery/friday-sh/ci.yml?branch=master&logo=githubactions&label=CI)](https://github.com/oornnery/friday-sh/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/oornnery/friday?logo=opensourceinitiative&label=License)](LICENSE)

LLM-powered shell agent that lives in your ZSH terminal.

```text
friday:auto(glm-5-turbo)> explain why this test is failing
```

Friday is a conversational AI assistant with coding, debugging, and
documentation modes. It routes tasks to specialized sub-agents,
remembers context across sessions, and integrates with your shell
workflow via keybindings and completions.

## Quick Start

### Install with uvx (no clone needed)

```bash
uvx --from git+https://github.com/oornnery/friday-sh friday chat
```

### Install with uv tool (global)

```bash
uv tool install git+https://github.com/oornnery/friday-sh
friday chat
```

### Install from source

```bash
git clone https://github.com/oornnery/friday-sh.git
cd friday
uv sync --group dev --group test
```

### Set up API keys

```bash
cp .env.example .env
# Edit .env with at least one provider key
```

```bash
# Anthropic
ANTHROPIC_API_KEY=

# OpenAI
OPENAI_API_KEY=

# Mistral
MISTRAL_API_KEY=

# Z.AI (ZhipuAI / GLM)
ZAI_API_KEY=
ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
```

### ZSH plugin

Source the plugin in your `.zshrc`:

```bash
source /path/to/friday/src/friday/shell/friday.plugin.zsh
```

Now use `f` from anywhere in your shell:

```bash
f "why did my last command fail?"
f "how do I use find to delete tmp files?"
```

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- At least one LLM provider key (or local Ollama)

## Usage

### CLI

```bash
# Ask a single question (uses router agent by default)
friday ask "explain this error"

# Pipe input
cat error.log | friday ask "what went wrong?"
git diff | friday ask "review this"

# Force a specific mode
friday ask --mode debug "why is pytest failing?"
friday ask --mode reader "explain the router module"

# Use a specific model
friday ask --model mistral:codestral-latest "refactor this function"

# Interactive chat
friday chat
friday chat --mode code --model zai:glm-5-turbo
```

### REPL

The chat REPL has a styled prompt showing mode and model:

```text
friday:auto(glm-5-turbo)> hello
friday:code(codestral-latest)> fix the failing test
friday:debug(glm-5-turbo)[debug]> /mode show
```

Commands:

```text
  /model       Interactive model picker (or /model show | /model <name>)
  /mode        Interactive mode picker (or /mode show | /mode <name>)
  /session     Resume session picker (or /session show | resume | new | delete)
  /setting     Show settings (or /setting <key> | /setting <key>=<value>)
  /memory      List memories (or /memory show | search | add | delete)
  /debug       Toggle debug (or /debug on | off | show)
  /clear       Clear conversation
  /quit        Exit Friday
```

Type `@` to trigger file completion, `/` for command completion.

The `/model` and `/mode` pickers support **search** -- type to filter:

```text
  Select model  (3/87)
  / glm
    zai:glm-4.5
  > zai:glm-5-turbo  (active)
    zai:glm-5.1
```

### ZSH Keybindings

| Key                   | Action                                                  |
| --------------------- | ------------------------------------------------------- |
| `f "question"`        | Ask Friday from anywhere                                |
| `Ctrl+F`              | Compose `f` command from current buffer or last command |
| `Ctrl+G`              | Fuzzy session picker (requires fzf)                     |
| `friday-select-model` | Interactive model picker with fzf                       |

**Piping input:**

```bash
git status | f                        # Friday sees the output
git diff | f "review this"            # Pipe + question combined
cat error.log | f "what went wrong?"  # Analyze any output
```

**Ctrl+F in action:**

```text
# You type a command that fails:
$ whoemi
zsh: command not found: whoemi

# Press Ctrl+F — Friday composes the question for you:
$ f "last command: whoemi (exit 127)"
# Press Enter to ask
```

**Ctrl+G session picker:**

```text
friday session>
  3/3
  20260409-162219-69b3a6  2026-04-09 16:22  2t  hello
  20260409-155731-316ce7  2026-04-09 15:57  3t  explain the router module
  20260409-154629-9355d4  2026-04-09 15:46  1t  fix the failing test
```

### Resource Commands (CLI)

```bash
friday model show                 # List all models from providers
friday model set                  # Interactive picker
friday mode show                  # List modes
friday session show               # List saved sessions
friday session resume <id>        # Resume session
friday setting show               # Show all settings
friday memory show                # List shared memories
friday memory add "user prefers concise answers"
friday memory search "preferences"
```

## Architecture

```text
                          +-------------------+
                          |     ZSH Shell     |
                          |  f "question"     |
                          |  Ctrl+F / Ctrl+G  |
                          +---------+---------+
                                    |
                          +---------v---------+
                          |    friday CLI     |
                          |  ask | chat       |
                          +---------+---------+
                                    |
                    +---------------v---------------+
                    |        Router Agent            |
                    |   (auto mode -- conversational)|
                    +--+--------+--------+--------+-+
                       |        |        |        |
              +--------v--+ +---v----+ +-v------+ +--v-------+
              | Code Agent| | Reader | | Writer | |  Debug   |
              | read,write| | read   | | read,  | | read,    |
              | patch,    | | list,  | | write, | | list,    |
              | shell,    | | search | | list,  | | search,  |
              | search    | |        | | search | | shell    |
              +-----------+ +--------+ +--------+ +----------+
                       |        |        |        |
                    +--v--------v--------v--------v--+
                    |         Tool Layer              |
                    |  filesystem | shell | memory    |
                    +---------------+----------------+
                                    |
                    +---------------v---------------+
                    |        Infrastructure          |
                    | config | sessions | memory.db  |
                    | MCP servers | model providers  |
                    +-------------------------------+
```

### Agent Modes

| Mode       | Purpose                        | Tools                                   |
| ---------- | ------------------------------ | --------------------------------------- |
| **auto**   | Routes to the right specialist | delegation only                         |
| **code**   | Write, edit, test code         | read, write, patch, list, search, shell |
| **reader** | Analyze and explain code       | read, list, search                      |
| **write**  | Generate docs and text         | read, write, list, search               |
| **debug**  | Diagnose errors and bugs       | read, list, search, shell               |

Each mode is defined in `src/friday/agent/prompts/<mode>.md` with YAML
frontmatter specifying tools, max steps, model override, and thinking.

### Approval System

Risky tools (`write_file`, `patch_file`, `run_shell`) require user
confirmation before executing:

```text
╭── Confirm ─────────────────────────────╮
│ run_shell: execute deferred tool call  │
│                                        │
│ { "command": "rm -rf node_modules" }   │
╰────────────────────────────────────────╯
Allow?  y / N
```

In non-interactive contexts (CLI `friday ask`), the picker style is used:

```text
  Allow?
> Yes
  No
```

Configurable via `approval_policy`:

- **ask** (default) -- prompt for each risky action
- **auto** -- execute without asking
- **never** -- always deny

### Memory System

Friday has three layers of memory:

```text
  +---------------------------+
  | Shared Memory (SQLite)    |  <-- cross-session, searchable
  | profile, preferences,     |      agent saves via save_memory
  | notes, decisions          |
  +---------------------------+
  | Working Memory            |  <-- per-session, short-term
  | task, files, notes,       |      auto-managed by harness
  | entities, decisions       |
  +---------------------------+
  | Message History           |  <-- per-session transcript
  | pydantic-ai messages      |      trimmed by history processor
  +---------------------------+
```

The agent decides what to save to shared memory via the `save_memory`
tool. The harness indexes chat turns for cross-session search.

### Supported Providers

| Prefix       | Provider           | Auth                |
| ------------ | ------------------ | ------------------- |
| `anthropic:` | Anthropic (Claude) | `ANTHROPIC_API_KEY` |
| `openai:`    | OpenAI (GPT)       | `OPENAI_API_KEY`    |
| `mistral:`   | Mistral AI         | `MISTRAL_API_KEY`   |
| `zai:`       | Z.AI (GLM)         | `ZAI_API_KEY`       |
| `ollama:`    | Ollama (local)     | no key needed       |

Model fallback: if the default model fails (missing key), Friday
automatically tries `fallback_model` from config.

### MCP Integration

Friday supports [Model Context Protocol](https://modelcontextprotocol.io/)
servers. Configure in `~/.config/friday/config.toml`:

```toml
[[mcp_servers]]
name = "github"
transport = "http"
url = "http://localhost:3000/mcp"

[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
```

## Configuration

Friday reads config from (in priority order):

1. Environment variables (`FRIDAY_*` prefix)
2. `.env` file
3. `~/.config/friday/config.toml` or `friday.toml`

### Settings

| Key               | Default                          | Description               |
| ----------------- | -------------------------------- | ------------------------- |
| `default_model`   | `zai:glm-5-turbo`                | Default LLM               |
| `fallback_model`  | `mistral:devstral-latest`        | Fallback if default fails |
| `default_mode`    | `auto`                           | Default agent mode        |
| `approval_policy` | `ask`                            | Risky tool confirmation   |
| `max_steps`       | `25`                             | Max tool calls per turn   |
| `session_dir`     | `~/.local/share/friday/sessions` | Session storage           |
| `config_dir`      | `~/.config/friday`               | Config directory          |
| `memory_db_path`  | `memory.db`                      | SQLite memory database    |
| `memory_top_k`    | `6`                              | Memory results per turn   |

Runtime override in chat: `/setting default_model=mistral:codestral-latest`

## Project Structure

```text
src/friday/
|-- __init__.py              # package version
|-- __main__.py              # python -m friday
|
|-- agent/                   # core AI runtime
|   |-- core.py              # agent factory, execution loop, approval flow
|   |-- router.py            # delegation tools (delegate_code, etc.)
|   |-- memory.py            # shared memory retrieval + chat indexing
|   |-- context.py           # workspace snapshot (git, env, shell state)
|   |-- contracts.py         # AgentReply, RouterDecision, TurnOutput
|   |-- deps.py              # AgentDeps injected into tools
|   |-- modes.py             # mode config loader (YAML frontmatter)
|   |-- history.py           # history trimming (pair-safe, dedup)
|   |-- stats.py             # token/cost tracking per turn
|   `-- prompts/             # system prompts per mode
|       |-- router.md        # auto mode -- conversational router
|       |-- code.md          # code mode -- full access
|       |-- reader.md        # reader mode -- read-only
|       |-- writer.md        # writer mode -- docs generation
|       `-- debug.md         # debug mode -- error diagnosis
|
|-- cli/                     # terminal interface
|   |-- app.py               # typer entrypoint + all CLI commands
|   |-- chat.py              # interactive REPL loop
|   |-- ask.py               # single-shot ask
|   |-- catalog.py           # command registry (REPL + CLI)
|   |-- completer.py         # / commands + @ file completion
|   |-- picker.py            # interactive list picker with search
|   |-- confirm.py           # approval dialogs for risky tools
|   |-- models.py            # dynamic model listing from providers
|   |-- resources.py         # interactive pickers for model/mode/session
|   |-- output.py            # rich console, markdown rendering
|   |-- theme.py             # unified color palette
|   `-- debug.py             # debug mode logging
|
|-- domain/                  # pure business logic (no IO)
|   |-- models.py            # AgentMode, WorkingMemory, MemoryKind
|   |-- validation.py        # input limits (path, command, content)
|   `-- permissions.py       # safe_path, contains_secret, clip
|
|-- infra/                   # IO boundary
|   |-- config.py            # FridaySettings (pydantic-settings)
|   |-- sessions.py          # JSON session store
|   |-- memory.py            # SQLite + FTS5 shared memory
|   `-- mcp.py               # MCP server factory
|
|-- tools/                   # pydantic-ai tool implementations
|   |-- filesystem.py        # read, write, patch, list, search
|   |-- shell.py             # run_shell with validation
|   |-- memory.py            # search_memory, save_memory, list_memories
|   `-- registry.py          # tool metadata
|
`-- shell/
    `-- friday.plugin.zsh    # ZSH integration (f, Ctrl+F, Ctrl+G)
```

## Development

```bash
# Setup
git clone https://github.com/oornnery/friday-sh.git
cd friday
uv sync --group dev --group test

# Run all checks (format + lint + typecheck + test)
uv run task check

# Individual tasks
uv run task format      # ruff format
uv run task lint        # ruff check --fix
uv run task typecheck   # ty check
uv run task test        # pytest -v

# Run a single test
uv run pytest tests/test_security.py::TestContainsSecret -v

# Run friday locally
uv run friday chat
uv run friday ask "hello"
```

## License

MIT
