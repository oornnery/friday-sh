# Friday — LLM Shell Agent

> Historical plan. This document describes the original v1 direction and no longer matches the current Friday v2 command surface or runtime.

## Context

O projeto "friday" é um agente LLM que funciona como extensão ZSH. O objetivo é ter um assistente de shell inteligente que pode ver saída de comandos, recomendar soluções, codificar, e operar em diferentes modos. Atualmente o projeto é um esqueleto vazio (só `main.py` com hello world).

## Stack

- **Runtime**: Python 3.13, uv
- **Agent framework**: pydantic-ai (ReAct loop, tool calling, multi-model, MCP client)
- **CLI**: typer
- **Output**: rich
- **Input interativo**: prompt_toolkit
- **Validação**: pydantic + pydantic-settings
- **Config**: TOML + env vars

## Arquitetura

```
src/friday/
├── __init__.py
├── __main__.py
├── domain/
│   ├── models.py          # AgentMode(StrEnum), WorkingMemory, Session, RuntimeContext
│   └── permissions.py     # safe_path(), ApprovalPolicy(StrEnum)
├── agent/
│   ├── core.py            # FridayAgent — wrapper pydantic-ai com context/memory
│   ├── modes.py           # ModeConfig por modo (system prompt, tools, max_steps)
│   └── context.py         # WorkspaceContext.discover() — git, env, shell state
├── tools/
│   ├── registry.py        # FridayTool dataclass, TOOL_REGISTRY dict
│   ├── filesystem.py      # read_file, write_file, patch_file, list_files, search
│   └── shell.py           # run_shell com timeout e safe_path
├── infra/
│   ├── config.py          # FridaySettings(BaseSettings) — toml + env
│   ├── sessions.py        # JsonSessionStore — ~/.local/share/friday/sessions/
│   └── mcp.py             # create_mcp_servers() wrapping pydantic-ai MCP
├── cli/
│   ├── app.py             # typer.Typer main, entry point
│   ├── chat.py            # `friday chat` — REPL interativo com prompt_toolkit
│   ├── ask.py             # `friday ask "pergunta"` — single-shot
│   └── output.py          # Rich console, markdown rendering, streaming
└── shell/
    └── friday.plugin.zsh  # ZSH plugin: f(), Ctrl+F widget, precmd hook
```

## Por que pydantic-ai

- Já implementa o ReAct loop (não precisa reimplementar o `Agent.ask()` do building-agents skill)
- Multi-model nativo (Anthropic, OpenAI, Ollama, OpenRouter)
- MCP client built-in (`MCPServerHTTP`, `MCPServerStdio`)
- Tools tipados com `RunContext` e dependency injection
- Streaming responses nativo
- Structured output via pydantic models
- Friday adiciona por cima: modos, permissions, sessions, ZSH integration

## Modos

| Modo | Foco | Tools |
|------|------|-------|
| `code` | Codificar, editar, testar | fs + shell + delegate |
| `reader` | Ler, analisar, explicar | read_file, list_files, search |
| `write` | Gerar docs, READMEs | read_file, write_file, search |
| `debug` | Diagnosticar erros, trace | fs + shell + web |

**v1 implementa só `code` mode.** Os outros modos são a mesma estrutura com configs diferentes.

## ZSH Integration

1. **CLI direto**: `friday ask "por que falhou?"`, `friday chat`
2. **Plugin ZSH** (`friday.plugin.zsh`):
   - `f "pergunta"` — shorthand
   - `Ctrl+F` — widget que captura buffer + último comando
   - `precmd` hook — salva `FRIDAY_LAST_EXIT` e `FRIDAY_LAST_CMD`
   - **fzf integration**:
     - `Ctrl+G` — fuzzy search no histórico de sessões/respostas
     - `friday history | fzf` — buscar comandos sugeridos anteriormente
     - Completions no REPL estilo Claude Code:
       - `/` — lista comandos disponíveis com help (`/mode`, `/model`, `/session`, `/clear`, `/quit`)
       - `@` — fuzzy file picker (arquivos do cwd via fzf)
       - Tab — completions de subcomandos, modos, modelos disponíveis
     - `friday models | fzf` — listar e selecionar modelo interativamente
3. RuntimeContext lê essas env vars para ter consciência do shell

## Config

`~/.config/friday/config.toml` + env vars `FRIDAY_*`:

```toml
default_model = "anthropic:claude-sonnet-4-20250514"
default_mode = "code"
approval_policy = "ask"

[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
```

## Plano de Implementação (v1)

### Passo 1 — Scaffold do projeto
- Criar estrutura `src/friday/` com `__init__.py` em cada módulo
- Atualizar `pyproject.toml` com dependências e entry point `[project.scripts] friday = "friday.cli.app:main"`
- `uv sync`
- **Arquivos**: `pyproject.toml`, todos os `__init__.py`, `src/friday/__main__.py`

### Passo 2 — Domain models + permissions
- `AgentMode(StrEnum)`, `ApprovalPolicy(StrEnum)`
- `WorkingMemory`, `Session` dataclasses
- `safe_path()`, `clip()`
- **Arquivos**: `src/friday/domain/models.py`, `src/friday/domain/permissions.py`

### Passo 3 — Config
- `FridaySettings(BaseSettings)` com pydantic-settings
- TOML + env vars, `MCPServerConfig`
- **Arquivo**: `src/friday/infra/config.py`

### Passo 4 — WorkspaceContext
- `WorkspaceContext.discover()` — git info, env vars, shell state
- `render()` para system prompt
- **Arquivo**: `src/friday/agent/context.py`

### Passo 5 — Tools
- `FridayTool` dataclass + registry
- `read_file`, `write_file`, `patch_file`, `list_files`, `search` (ripgrep)
- `run_shell` com timeout e approval
- **Arquivos**: `src/friday/tools/registry.py`, `tools/filesystem.py`, `tools/shell.py`

### Passo 6 — Agent core
- `ModeConfig` dataclass por modo
- `FridayAgent` wrapping pydantic-ai `Agent`
- `create_agent(mode, config, context)` factory
- **Arquivos**: `src/friday/agent/modes.py`, `src/friday/agent/core.py`

### Passo 7 — CLI
- `typer.Typer` com `chat`, `ask`, `config` commands
- Rich output com markdown rendering e streaming
- prompt_toolkit para REPL input
- **Arquivos**: `src/friday/cli/app.py`, `cli/chat.py`, `cli/ask.py`, `cli/output.py`

### Passo 8 — Sessions
- `JsonSessionStore` — save/load/resume
- Context reduction com `render_history()`
- **Arquivo**: `src/friday/infra/sessions.py`

### Passo 9 — ZSH plugin + fzf
- `friday.plugin.zsh` com `f()`, widget, precmd hook
- fzf: `Ctrl+G` sessões, completions `/` `@` Tab, `friday models | fzf`
- REPL slash commands: `/mode`, `/model`, `/session`, `/clear`, `/quit`, `/help`
- `@` file picker com fzf no REPL
- **Arquivo**: `src/friday/shell/friday.plugin.zsh`

### Passo 10 — Tests
- `FakeModelClient` para testar o loop
- Tests para permissions, tools, CLI
- **Arquivos**: `tests/`

## Defer (v2+)

- Modos reader, write, debug (mesma estrutura, configs diferentes)
- Skills system (discovery, triggers, skill.toml)
- Custom agents/commands discovery
- MCP server connections (plumbing já existe via pydantic-ai)
- Web tools (fetch_url, web_search)
- model_query tool (perguntar a outro LLM)
- Subagents / delegation
- Hooks system (before_tool, after_tool)
- Background tasks
- ZSH output capture avançado

## Verificação

```bash
uv sync                              # deps instaladas
uv run ruff check src/               # lint passa
uv run ty check                      # types passam
uv run pytest -v                     # tests passam
uv run friday --help                 # CLI funciona
uv run friday ask "hello"            # single-shot funciona
uv run friday chat                   # REPL funciona
```
