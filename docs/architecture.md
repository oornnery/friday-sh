# friday -- Architecture

## Overview

friday is a multi-agent LLM system that runs inside ZSH. It uses a
**router agent** to classify user intent and delegate to specialized
sub-agents. Each sub-agent has a different set of tools and constraints.

## System Flow

```text
  User
    |
    v
  +------------------+     +------------------+
  | ZSH Shell        |     | friday CLI       |
  | f "question"     |---->| ask | chat       |
  | Ctrl+F / Ctrl+G  |     +--------+---------+
  +------------------+              |
                                    v
                          +---------+---------+
                          |   Router Agent    |
                          |   (auto mode)     |
                          |                   |
                          | Decides:          |
                          | - respond directly|
                          | - delegate to     |
                          |   specialist      |
                          +--+--+--+--+-------+
                             |  |  |  |
                +------------+  |  |  +------------+
                |               |  |               |
                v               v  v               v
          +----------+  +--------+ +--------+ +----------+
          |   Code   |  | Reader | | Writer | |  Debug   |
          |  Agent   |  | Agent  | | Agent  | |  Agent   |
          +----+-----+  +---+----+ +---+----+ +----+-----+
               |             |         |            |
               +------+------+---------+------+-----+
                      |                       |
                      v                       v
               +------+------+        +-------+------+
               | Tool Layer  |        | Memory Layer |
               | filesystem  |        | SQLite FTS5  |
               | shell       |        | search/save  |
               +------+------+        +-------+------+
                      |                       |
                      v                       v
               +------+------+        +-------+------+
               | Workspace   |        | Sessions     |
               | (git, env)  |        | (JSON files) |
               +--------------+       +--------------+
```

## Module Map

```text
src/friday/
|
|-- agent/                          CORE RUNTIME
|   |-- core.py                     Agent factory + execution loop
|   |                               - create_agent(mode) -> Agent
|   |                               - execute_agent() -> ExecutedTurn
|   |                               - _resolve_model() with fallback
|   |                               - _build_toolsets() with approval
|   |                               - _resolve_deferred_requests()
|   |
|   |-- router.py                   Delegation tools for auto mode
|   |                               - delegate_code/reader/writer/debug
|   |                               - _run_sub_agent() -> AgentReply
|   |
|   |-- memory.py                   Shared memory orchestration
|   |                               - load_relevant_shared_memory()
|   |                               - sync_shared_memory_to_working_memory()
|   |                               - record_completed_turn() (chat indexing)
|   |
|   |-- context.py                  Workspace snapshot (frozen)
|   |                               - WorkspaceContext.discover()
|   |                               - git branch, status, commits
|   |                               - shell env (sanitized)
|   |
|   |-- contracts.py                Type contracts
|   |                               - AgentReply (markdown, status, files)
|   |                               - RouterDecision (respond | delegate)
|   |                               - TurnOutput = AgentReply | Deferred
|   |
|   |-- deps.py                     AgentDeps dataclass
|   |                               - workspace_root, context, settings
|   |                               - memory, memory_store, shared_memory
|   |                               - session_id, interactive, turn_stats
|   |
|   |-- modes.py                    Mode config from YAML frontmatter
|   |                               - ModePromptConfig (tools, max_steps, etc.)
|   |                               - MODE_CONFIGS dict
|   |
|   |-- history.py                  History trimming
|   |                               - pair-safe user-turn boundaries
|   |                               - dedup old read_file calls
|   |                               - clip old text/tool results
|   |
|   |-- stats.py                    Token/cost tracking
|   |                               - TurnStats accumulator
|   |                               - format_turn_summary()
|   |
|   `-- prompts/                    System prompts (markdown + frontmatter)
|       |-- router.md               auto mode (no tools, structured output)
|       |-- code.md                 full access (read, write, patch, shell)
|       |-- reader.md               read-only (read, list, search)
|       |-- writer.md               docs (read, write, list, search)
|       `-- debug.md                diagnosis (read, list, search, shell)
|
|-- cli/                            TERMINAL INTERFACE
|   |-- app.py                      Typer entrypoint, all CLI commands
|   |-- chat.py                     REPL loop (single event loop)
|   |-- ask.py                      Single-shot ask
|   |-- catalog.py                  REPL_COMMANDS + RESOURCE_COMMANDS
|   |-- completer.py                / commands + @ file completions
|   |-- picker.py                   Interactive list with search + scroll
|   |-- confirm.py                  Approval dialogs for risky tools
|   |-- models.py                   Dynamic model listing from APIs
|   |-- resources.py                Interactive pickers (model/mode/session)
|   |-- output.py                   Rich console + markdown + panels
|   |-- theme.py                    Unified color palette (rich + pt)
|   `-- debug.py                    Debug logging toggle
|
|-- domain/                         PURE LOGIC (no IO)
|   |-- models.py                   AgentMode, WorkingMemory, MemoryKind
|   |-- validation.py               Input limits (path, command, content)
|   `-- permissions.py              safe_path, contains_secret, clip
|
|-- infra/                          IO BOUNDARY
|   |-- config.py                   FridaySettings (pydantic-settings)
|   |-- sessions.py                 JSON session store (v2 schema)
|   |-- memory.py                   SQLite + FTS5 shared memory
|   `-- mcp.py                      MCP server factory
|
|-- tools/                          PYDANTIC-AI TOOLS
|   |-- filesystem.py               read, write, patch, list, search
|   |-- shell.py                    run_shell (validated, capped)
|   |-- memory.py                   search_memory, save_memory, list_memories
|   `-- registry.py                 Tool metadata
|
`-- shell/
    `-- friday.plugin.zsh           ZSH integration
```

## Data Flow: A Single Turn

```text
  User types: "fix the failing test"
         |
         v
  1. REPL reads input
         |
         v
  2. _prepare_turn()
     - load_relevant_shared_memory(prompt)
     - sync_shared_memory_to_working_memory()
         |
         v
  3. execute_agent(router, prompt)
     - Router returns RouterDecision(delegate, mode=code, task=...)
         |
         v
  4. _run_specialist_from_auto(code, task)
     - create_agent(CODE)
     - execute_agent(code_agent, task)
       |
       +-- agent calls read_file("tests/test_foo.py")
       +-- agent calls run_shell("pytest tests/test_foo.py -v")
       |   +-- approval prompt (if policy=ask)
       +-- agent calls patch_file("src/foo.py", old, new)
       |   +-- approval prompt
       +-- agent calls run_shell("pytest tests/test_foo.py -v")
       +-- agent returns AgentReply(markdown="Fixed...")
         |
         v
  5. record_completed_turn()
     - index chat chunk for cross-session search
         |
         v
  6. Display: print_markdown(reply) + print_run_summary(stats)
         |
         v
  7. Save session to disk
```

## Memory Architecture

```text
  +------------------------------------------+
  |          SQLite Database                  |
  |  ~/.config/friday/memory.db              |
  |                                          |
  |  +------------------------------------+  |
  |  | memory_records                     |  |
  |  | id | text | kind | scope | pinned  |  |
  |  +------------------------------------+  |
  |  | memory_records_fts (FTS5)          |  |
  |  +------------------------------------+  |
  |                                          |
  |  +------------------------------------+  |
  |  | chat_chunks                        |  |
  |  | session_id | user_prompt | reply   |  |
  |  +------------------------------------+  |
  |  | chat_chunks_fts (FTS5)             |  |
  |  +------------------------------------+  |
  +------------------------------------------+

  Memory Kinds:
    profile     - user identity (name, role)
    preference  - user preferences
    workflow    - recurring patterns
    decision    - project decisions
    project_fact - project-specific facts
    note        - general notes

  Scopes:
    global - available across all workspaces
    repo   - scoped to current git repo
```

## Tool Security

```text
  Tool Call
    |
    v
  Input Validation (domain/validation.py)
    - path length <= 500
    - pattern length <= 200, no ..
    - command length <= 2000
    - content length <= 100K
    - line range 1..10K
    |
    v
  Path Containment (domain/permissions.py)
    - safe_path() resolves symlinks
    - rejects escapes outside workspace
    |
    v
  Secret Detection (domain/permissions.py)
    - contains_secret() checks 7 patterns
    - sanitize_for_prompt() redacts secrets
    |
    v
  Approval (agent/core.py + cli/confirm.py)
    - risky tools wrapped in ApprovalRequiredToolset
    - policy: ask | auto | never
    - audit logged at INFO level
    |
    v
  Execution
    - shell output capped at 8K
    - subprocess timeout max 120s
    - MCP commands blocklisted for bare shells
```

## Session Persistence

```text
  ~/.local/share/friday/sessions/
    20260409-154629-9355d4.json
    20260409-143022-a1b2c3.json
    ...

  SessionEnvelope (v2):
    schema_version: 2
    meta:
      id, created_at, model, mode
      turn_count, last_user_message
      workspace_key
    messages:
      list[ModelMessage]  (pydantic-ai native)
```

## Configuration Layers

```text
  Priority (highest first):
    1. FridaySettings(**init_kwargs)
    2. FRIDAY_* environment variables
    3. .env file (loaded by python-dotenv)
    4. ~/.config/friday/config.toml
    5. ./friday.toml
```
