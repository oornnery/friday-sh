# Friday v3: memória compartilhada, busca cross-chat e isolamento correto de sessão

## Resumo
- Separar definitivamente os 3 níveis de estado do agente:
  - `WorkspaceContext`: snapshot do workspace atual
  - `Session transcript + WorkingMemory`: estado da sessão atual
  - `Shared long-term memory`: memória persistente global, compartilhada entre chats
- Implementar busca cross-chat nesta rodada com `SQLite + FTS5` agora, com schema e abstração já prontos para plugar embeddings reais depois.
- Corrigir o vazamento atual de `WorkingMemory` entre sessões no mesmo REPL.
- Adicionar uma nova superfície pública `memories` para inspecionar, salvar, buscar e apagar memória compartilhada.

## Mudanças de Implementação
### Modelo de memória
- Manter `SessionEnvelope` como transcript da sessão atual, sem misturar long-term memory dentro do JSON da sessão.
- Criar um `MemoryStore` com implementação `SQLiteMemoryStore` em um banco local único, por padrão em `~/.config/friday/memory.db`.
- Adicionar tipos explícitos:
  - `MemoryScope = global | repo`
  - `MemoryKind = profile | preference | project_fact | decision | workflow | note`
  - `MemoryRecord`
  - `ChatChunk`
  - `MemorySearchResult`
- Persistir 2 corpora separados no banco:
  - `memory_records`: fatos/prompts promovidos para memória persistente
  - `chat_chunks`: trechos indexáveis derivados de outros chats
- Indexar `chat_chunks` por turno concluído do usuário, não por mensagem bruta:
  - guardar user prompt + resposta final do agente + `session_id` + `workspace_key` + timestamps
  - não indexar tool chatter bruto nem mensagens parciais
- Usar `workspace_key = repo_root.resolve().as_posix()` para escopo por projeto.
- Criar FTS5 para `memory_records` e `chat_chunks`, com ranking BM25 + rerank local:
  - boost para `repo` matching
  - boost para memórias `pinned`
  - preferência leve para `memory_records` sobre `chat_chunks` quando score for parecido
  - recência como desempate

### Leitura da memória
- Em cada turno top-level com `user_prompt`, consultar:
  - memória compartilhada do repo atual
  - memória global
  - chunks relevantes de outros chats
- Injetar o resultado em uma seção nova das `instructions`, separada de `WorkingMemory`, por exemplo `## Relevant Shared Memory`.
- Limitar o snapshot injetado:
  - no máximo 3 `memory_records`
  - no máximo 3 `chat_chunks`
  - cada item clipped
- O agente não terá acesso automático ao transcript completo de outros chats, só aos snippets recuperados.
- Adicionar tools seguras para uso on-demand pelo agente:
  - `search_memory(query: str)`
  - `save_memory(text: str, kind: MemoryKind = note, scope: MemoryScope = global, pinned: bool = false)`
  - `list_memories(limit: int = 20, scope: MemoryScope | None = None)`
- `search_memory` deve buscar em `memory_records` e `chat_chunks`, retornando fonte, score, `session_id` quando aplicável, e snippet.

### Escrita da memória
- Política híbrida:
  - gravação explícita via `memories set` e `save_memory`
  - auto-promoção conservadora após turnos concluídos
- Auto-promoção deve usar pipeline em 2 etapas:
  - gate heurístico barato para detectar turnos potencialmente persistentes
  - extração estruturada pequena para gerar candidatos `MemoryRecord`
- Auto-promoção só deve salvar fatos estáveis e úteis:
  - nome do usuário
  - preferências persistentes
  - convenções de projeto
  - decisões aceitas
  - workflows recorrentes
- Nunca auto-salvar:
  - segredos
  - raw tool output
  - erros transitórios
  - comandos one-off
  - suposições do modelo
- Deduplicar por `(normalized_text, scope, workspace_key)` com merge/upsert em vez de criar duplicatas.

### Sessão, working memory e contexto
- `WorkingMemory` deixa de ser só `task/files/notes` e passa a incluir também:
  - `entities`
  - `decisions`
- `WorkingMemory` continua sendo curta, mutável e só da sessão atual.
- Resetar `WorkingMemory` em:
  - `/clear`
  - `/sessions set`
  - `/sessions new`
  - `run_chat_with_session(...)` ao abrir sessão salva
- Ao trocar de sessão, carregar:
  - transcript daquela sessão
  - modo/modelo daquela sessão
  - `WorkingMemory` vazia
  - shared memory será recuperada de novo por busca, não herdada da sessão anterior
- Evoluir a compactação de histórico além do corte por turnos:
  - dedupe de leituras antigas repetidas
  - mais fidelidade para turnos recentes
  - clipping agressivo para histórico velho
- `WorkspaceContext` continua isolado e recalculado do ambiente atual; ele não vira memória persistente.

## Interfaces Públicas
- Nova CLI:
  - `friday memories`
  - `friday memories list`
  - `friday memories search <query>`
  - `friday memories set <text>`
  - `friday memories get <id>`
  - `friday memories delete [id]`
- Nova REPL:
  - `/memories`
  - `/memories list`
  - `/memories search <query>`
  - `/memories set <text>`
  - `/memories get <id>`
  - `/memories delete [id]`
- Regras de UX:
  - ação padrão de `memories` = `list`
  - `get` e `delete` abrem picker em TTY quando faltar ID
  - `set` salva memória explícita com defaults:
    - `kind = note`
    - `scope = global`
    - `pinned = true`
- Novas settings:
  - `memory_db_path`
  - `memory_top_k`
  - `memory_auto_promote`
- Defaults:
  - `memory_db_path = ~/.config/friday/memory.db`
  - `memory_top_k = 6`
  - `memory_auto_promote = true`

## Testes
- Sessão e isolamento:
  - trocar de sessão no REPL não pode vazar `WorkingMemory`
  - `/clear` e `/sessions new` resetam memória curta
  - transcript continua específico da sessão ativa
- Shared memory:
  - `memories set` cria registro persistente
  - busca retorna itens `repo` e `global`
  - repo atual recebe boost sobre memória global
  - dedupe/upsert não cria registros duplicados
- Cross-chat:
  - chat chunks de outra sessão ficam pesquisáveis
  - retrieval injeta só snippets relevantes, não transcript inteiro
  - resultado deve citar a origem `memory` vs `chat` e `session_id` quando vier de chat
- Auto-promoção:
  - captura “meu nome é Fabio”, preferências e decisões aceitas
  - não salva segredos nem ruído transitório
- Runtime:
  - `search_memory` e `save_memory` aparecem nos modos corretos
  - `Relevant Shared Memory` entra nas instructions do turno
  - compactação de histórico continua pair-safe
- Quality gates:
  - `ruff check`
  - `ty check --exclude 'tests/'`
  - `pytest`

## Assunções e Defaults
- Esta rodada entrega busca cross-chat boa com FTS/BM25 local, não semantic search por embeddings ainda.
- O schema e a abstração devem nascer prontos para uma rodada futura de embeddings sem quebrar a API pública.
- A memória compartilhada vale para dois escopos ao mesmo tempo:
  - `global`
  - `repo`
- O agente poderá consultar shared memory de outros chats por snippets relevantes, mas não navegar automaticamente por transcripts completos.
- A memória persistente continua separada do JSON da sessão, seguindo a recomendação do `building-agents`: transcript, working memory e long-term memory têm papéis diferentes.
