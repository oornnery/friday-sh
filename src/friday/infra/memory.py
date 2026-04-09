"""SQLite-backed shared memory and cross-chat retrieval."""

from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from friday.domain.models import MemoryKind, MemoryScope
from friday.domain.permissions import clip

__all__ = [
    'GLOBAL_WORKSPACE_KEY',
    'ChatChunk',
    'MemoryRecord',
    'MemorySearchResult',
    'MemoryStore',
    'SQLiteMemoryStore',
    'SharedMemorySnapshot',
]

GLOBAL_WORKSPACE_KEY = '*'
_TOKEN_RE = re.compile(r'[\w:-]+', re.UNICODE)
_SEARCH_CANDIDATE_LIMIT = 18
_STOPWORDS = frozenset(
    {
        'a',
        'an',
        'and',
        'as',
        'at',
        'com',
        'como',
        'da',
        'das',
        'de',
        'do',
        'dos',
        'e',
        'em',
        'eu',
        'i',
        'is',
        'me',
        'meu',
        'minha',
        'my',
        'na',
        'no',
        'o',
        'of',
        'or',
        'os',
        'para',
        'por',
        'qual',
        'que',
        'seu',
        'sua',
        'the',
        'to',
        'um',
        'uma',
        'user',
        'você',
        'voce',
        'what',
        'who',
        'your',
    }
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(text: str) -> str:
    return ' '.join(text.casefold().split())


def _effective_workspace_key(scope: MemoryScope, workspace_key: str) -> str:
    if scope is MemoryScope.GLOBAL:
        return GLOBAL_WORKSPACE_KEY
    return workspace_key


def _query_terms(query: str) -> list[str]:
    tokens = _TOKEN_RE.findall(query.casefold())
    filtered = [token for token in tokens if len(token) > 1 and token not in _STOPWORDS]
    if not filtered:
        filtered = [token for token in tokens if len(token) > 1]
    return filtered[:8]


_FTS5_OPERATORS = {'AND', 'OR', 'NOT', 'NEAR'}
_MAX_QUERY_LENGTH = 500


def _fts_escape_token(token: str) -> str:
    """Escape a single token for safe use in FTS5 MATCH queries."""
    # Strip FTS5 special chars: (), *, :, ^, +
    cleaned = token.replace('"', '""')
    for ch in ('(', ')', '*', ':', '^', '+'):
        cleaned = cleaned.replace(ch, '')
    return cleaned.strip()


def _fts_query(query: str) -> str:
    """Build a safe FTS5 query from user input."""
    truncated = query[:_MAX_QUERY_LENGTH]
    filtered = _query_terms(truncated)
    escaped = []
    for token in filtered[:8]:
        # Skip FTS5 operators that could alter query semantics
        if token.upper() in _FTS5_OPERATORS:
            continue
        clean = _fts_escape_token(token)
        if clean:
            escaped.append(f'"{clean}"')
    return ' OR '.join(escaped) if escaped else '""'


def _recency_boost(timestamp: str) -> float:
    try:
        created = datetime.fromisoformat(timestamp)
    except ValueError:
        return 0.0
    age_days = max((datetime.now(UTC) - created).total_seconds() / 86_400, 0.0)
    return max(0.0, 0.3 - min(age_days, 30.0) * 0.01)


def _overlap_boost(text: str, terms: list[str]) -> float:
    normalized = text.casefold()
    overlap = sum(1 for term in terms if term in normalized)
    if not terms:
        return 0.0
    return overlap / len(terms)


class MemoryRecord(BaseModel):
    """A durable memory saved outside the session transcript."""

    id: str
    text: str
    normalized_text: str
    kind: MemoryKind
    scope: MemoryScope
    workspace_key: str
    pinned: bool = False
    created_at: str
    updated_at: str


class ChatChunk(BaseModel):
    """An indexable top-level chat turn from another session."""

    id: str
    session_id: str
    workspace_key: str
    user_prompt: str
    assistant_reply: str
    created_at: str
    updated_at: str


class MemorySearchResult(BaseModel):
    """Unified retrieval result across explicit memory and chat history."""

    id: str
    source: Literal['memory', 'chat']
    score: float
    snippet: str
    workspace_key: str
    created_at: str
    scope: MemoryScope | None = None
    kind: MemoryKind | None = None
    pinned: bool = False
    session_id: str | None = None


class SharedMemorySnapshot(BaseModel):
    """Compact memory snippet bundle injected into the prompt."""

    records: list[MemorySearchResult] = Field(default_factory=list)
    chats: list[MemorySearchResult] = Field(default_factory=list)

    def render(self) -> str:
        if not self.records and not self.chats:
            return '- none'

        lines: list[str] = []
        if self.records:
            lines.append('Memories:')
            for result in self.records:
                scope = result.scope.value if result.scope is not None else '-'
                kind = result.kind.value if result.kind is not None else '-'
                lines.append(f'  - [{scope}/{kind}] {clip(result.snippet, 240)}')
        if self.chats:
            lines.append('Chats:')
            for result in self.chats:
                session = result.session_id or '-'
                lines.append(f'  - [session {session}] {clip(result.snippet, 280)}')
        return '\n'.join(lines)


class MemoryStore(Protocol):
    """Abstract shared memory interface."""

    def save_memory(
        self,
        text: str,
        *,
        kind: MemoryKind,
        scope: MemoryScope,
        workspace_key: str,
        pinned: bool,
    ) -> tuple[MemoryRecord, bool]: ...

    def list_memories(
        self,
        *,
        workspace_key: str,
        limit: int = 20,
        scope: MemoryScope | None = None,
    ) -> list[MemoryRecord]: ...

    def get_memory(self, memory_id: str) -> MemoryRecord | None: ...

    def delete_memory(self, memory_id: str) -> bool: ...

    def index_chat_turn(
        self,
        *,
        session_id: str,
        workspace_key: str,
        user_prompt: str,
        assistant_reply: str,
    ) -> ChatChunk: ...

    def search(
        self,
        query: str,
        *,
        workspace_key: str,
        current_session_id: str | None = None,
        limit: int = 6,
    ) -> list[MemorySearchResult]: ...

    def select_prompt_snapshot(
        self,
        query: str,
        *,
        workspace_key: str,
        current_session_id: str | None = None,
        memory_limit: int = 3,
        chat_limit: int = 3,
    ) -> SharedMemorySnapshot: ...


class SQLiteMemoryStore:
    """SQLite/FTS5 implementation of the shared memory store."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_ready = False

    def save_memory(
        self,
        text: str,
        *,
        kind: MemoryKind,
        scope: MemoryScope,
        workspace_key: str,
        pinned: bool,
    ) -> tuple[MemoryRecord, bool]:
        normalized_text = _normalize_text(text)
        now = _utcnow()
        effective_workspace_key = _effective_workspace_key(scope, workspace_key)

        with closing(self._connect()) as conn, conn:
            existing = conn.execute(
                (
                    'SELECT id, kind, pinned FROM memory_records '
                    'WHERE normalized_text = ? AND scope = ? AND workspace_key = ?'
                ),
                (normalized_text, scope.value, effective_workspace_key),
            ).fetchone()

            created = existing is None
            record_id = f'mem-{uuid.uuid4().hex[:10]}' if existing is None else str(existing['id'])
            stored_kind = kind.value
            stored_pinned = pinned
            if existing is not None:
                stored_kind = kind.value if kind is not MemoryKind.NOTE else str(existing['kind'])
                stored_pinned = bool(existing['pinned']) or pinned
                conn.execute(
                    (
                        'UPDATE memory_records SET text = ?, kind = ?, pinned = ?, updated_at = ? '
                        'WHERE id = ?'
                    ),
                    (text.strip(), stored_kind, int(stored_pinned), now, record_id),
                )
            else:
                conn.execute(
                    (
                        'INSERT INTO memory_records '
                        '(id, text, normalized_text, kind, scope, workspace_key, pinned, '
                        'created_at, updated_at) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
                    ),
                    (
                        record_id,
                        text.strip(),
                        normalized_text,
                        stored_kind,
                        scope.value,
                        effective_workspace_key,
                        int(stored_pinned),
                        now,
                        now,
                    ),
                )

            self._sync_memory_fts(conn, record_id, text.strip())

            row = conn.execute(
                'SELECT * FROM memory_records WHERE id = ?',
                (record_id,),
            ).fetchone()

        assert row is not None
        return self._memory_record_from_row(row), created

    def list_memories(
        self,
        *,
        workspace_key: str,
        limit: int = 20,
        scope: MemoryScope | None = None,
    ) -> list[MemoryRecord]:
        if scope is MemoryScope.GLOBAL:
            query = (
                'SELECT * FROM memory_records '
                'WHERE scope = ? '
                'ORDER BY pinned DESC, updated_at DESC '
                'LIMIT ?'
            )
            params: tuple[object, ...] = (MemoryScope.GLOBAL.value, limit)
        elif scope is MemoryScope.REPO:
            query = (
                'SELECT * FROM memory_records '
                'WHERE scope = ? AND workspace_key = ? '
                'ORDER BY pinned DESC, updated_at DESC '
                'LIMIT ?'
            )
            params = (MemoryScope.REPO.value, workspace_key, limit)
        else:
            query = (
                'SELECT * FROM memory_records '
                'WHERE (scope = ? OR (scope = ? AND workspace_key = ?)) '
                'ORDER BY pinned DESC, updated_at DESC '
                'LIMIT ?'
            )
            params = (MemoryScope.GLOBAL.value, MemoryScope.REPO.value, workspace_key, limit)
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._memory_record_from_row(row) for row in rows]

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute('SELECT * FROM memory_records WHERE id = ?', (memory_id,)).fetchone()
        if row is None:
            return None
        return self._memory_record_from_row(row)

    def delete_memory(self, memory_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            deleted = conn.execute('DELETE FROM memory_records WHERE id = ?', (memory_id,)).rowcount
            conn.execute('DELETE FROM memory_records_fts WHERE id = ?', (memory_id,))
        return deleted > 0

    def index_chat_turn(
        self,
        *,
        session_id: str,
        workspace_key: str,
        user_prompt: str,
        assistant_reply: str,
    ) -> ChatChunk:
        normalized_text = _normalize_text(f'{user_prompt}\n{assistant_reply}')
        clipped_user_prompt = clip(user_prompt.strip(), 2_000)
        clipped_reply = clip(assistant_reply.strip(), 6_000)
        now = _utcnow()

        with closing(self._connect()) as conn, conn:
            existing = conn.execute(
                'SELECT id FROM chat_chunks WHERE session_id = ? AND normalized_text = ?',
                (session_id, normalized_text),
            ).fetchone()
            chunk_id = f'chat-{uuid.uuid4().hex[:10]}' if existing is None else str(existing['id'])

            if existing is not None:
                conn.execute(
                    (
                        'UPDATE chat_chunks '
                        'SET workspace_key = ?, user_prompt = ?, assistant_reply = ?, '
                        'updated_at = ? '
                        'WHERE id = ?'
                    ),
                    (workspace_key, clipped_user_prompt, clipped_reply, now, chunk_id),
                )
            else:
                conn.execute(
                    (
                        'INSERT INTO chat_chunks '
                        '(id, session_id, workspace_key, user_prompt, assistant_reply, '
                        'normalized_text, created_at, updated_at) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
                    ),
                    (
                        chunk_id,
                        session_id,
                        workspace_key,
                        clipped_user_prompt,
                        clipped_reply,
                        normalized_text,
                        now,
                        now,
                    ),
                )

            combined_text = self._render_chat_text(clipped_user_prompt, clipped_reply)
            self._sync_chat_fts(conn, chunk_id, combined_text)
            row = conn.execute('SELECT * FROM chat_chunks WHERE id = ?', (chunk_id,)).fetchone()

        assert row is not None
        return self._chat_chunk_from_row(row)

    def search(
        self,
        query: str,
        *,
        workspace_key: str,
        current_session_id: str | None = None,
        limit: int = 6,
    ) -> list[MemorySearchResult]:
        query_terms = _query_terms(query)
        fts_query = _fts_query(query)
        if not fts_query:
            return []

        with closing(self._connect()) as conn:
            memory_rows = conn.execute(
                (
                    'SELECT memory_records.*, bm25(memory_records_fts) AS rank '
                    'FROM memory_records_fts '
                    'JOIN memory_records ON memory_records.id = memory_records_fts.id '
                    'WHERE memory_records_fts MATCH ? '
                    'AND (memory_records.scope = ? OR memory_records.workspace_key = ?) '
                    'LIMIT ?'
                ),
                (
                    fts_query,
                    MemoryScope.GLOBAL.value,
                    workspace_key,
                    max(limit * 3, _SEARCH_CANDIDATE_LIMIT),
                ),
            ).fetchall()
            chat_rows = conn.execute(
                (
                    'SELECT chat_chunks.*, bm25(chat_chunks_fts) AS rank '
                    'FROM chat_chunks_fts '
                    'JOIN chat_chunks ON chat_chunks.id = chat_chunks_fts.id '
                    'WHERE chat_chunks_fts MATCH ? '
                    'AND chat_chunks.workspace_key = ? '
                    'AND (? IS NULL OR chat_chunks.session_id != ?) '
                    'LIMIT ?'
                ),
                (
                    fts_query,
                    workspace_key,
                    current_session_id,
                    current_session_id,
                    max(limit * 3, _SEARCH_CANDIDATE_LIMIT),
                ),
            ).fetchall()

        results = [
            self._search_result_from_memory_row(row, workspace_key, query_terms)
            for row in memory_rows
        ]
        results.extend(self._search_result_from_chat_row(row, query_terms) for row in chat_rows)
        results.sort(key=lambda result: (result.score, result.created_at), reverse=True)
        return results[:limit]

    def select_prompt_snapshot(
        self,
        query: str,
        *,
        workspace_key: str,
        current_session_id: str | None = None,
        memory_limit: int = 3,
        chat_limit: int = 3,
    ) -> SharedMemorySnapshot:
        results = self.search(
            query,
            workspace_key=workspace_key,
            current_session_id=current_session_id,
            limit=max(memory_limit + chat_limit, 6),
        )
        records = [result for result in results if result.source == 'memory'][:memory_limit]
        chats = [result for result in results if result.source == 'chat'][:chat_limit]
        return SharedMemorySnapshot(records=records, chats=chats)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        if not self._schema_ready:
            self._ensure_schema(conn)
            self._schema_ready = True
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                kind TEXT NOT NULL,
                scope TEXT NOT NULL,
                workspace_key TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS memory_records_unique_idx
            ON memory_records (normalized_text, scope, workspace_key);

            CREATE TABLE IF NOT EXISTS chat_chunks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                workspace_key TEXT NOT NULL,
                user_prompt TEXT NOT NULL,
                assistant_reply TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS chat_chunks_unique_idx
            ON chat_chunks (session_id, normalized_text);

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_records_fts
            USING fts5(id UNINDEXED, text, tokenize = 'porter unicode61');

            CREATE VIRTUAL TABLE IF NOT EXISTS chat_chunks_fts
            USING fts5(id UNINDEXED, text, tokenize = 'porter unicode61');
            """
        )

    def _sync_memory_fts(self, conn: sqlite3.Connection, record_id: str, text: str) -> None:
        conn.execute('DELETE FROM memory_records_fts WHERE id = ?', (record_id,))
        conn.execute(
            'INSERT INTO memory_records_fts (id, text) VALUES (?, ?)',
            (record_id, text),
        )

    def _sync_chat_fts(self, conn: sqlite3.Connection, chunk_id: str, text: str) -> None:
        conn.execute('DELETE FROM chat_chunks_fts WHERE id = ?', (chunk_id,))
        conn.execute(
            'INSERT INTO chat_chunks_fts (id, text) VALUES (?, ?)',
            (chunk_id, text),
        )

    def _memory_record_from_row(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=str(row['id']),
            text=str(row['text']),
            normalized_text=str(row['normalized_text']),
            kind=MemoryKind(str(row['kind'])),
            scope=MemoryScope(str(row['scope'])),
            workspace_key=str(row['workspace_key']),
            pinned=bool(row['pinned']),
            created_at=str(row['created_at']),
            updated_at=str(row['updated_at']),
        )

    def _chat_chunk_from_row(self, row: sqlite3.Row) -> ChatChunk:
        return ChatChunk(
            id=str(row['id']),
            session_id=str(row['session_id']),
            workspace_key=str(row['workspace_key']),
            user_prompt=str(row['user_prompt']),
            assistant_reply=str(row['assistant_reply']),
            created_at=str(row['created_at']),
            updated_at=str(row['updated_at']),
        )

    def _search_result_from_memory_row(
        self,
        row: sqlite3.Row,
        workspace_key: str,
        query_terms: list[str],
    ) -> MemorySearchResult:
        base_score = -float(row['rank'])
        text = str(row['text'])
        score = (
            base_score
            + 0.2
            + _recency_boost(str(row['updated_at']))
            + _overlap_boost(text, query_terms)
        )
        if (
            str(row['workspace_key']) == workspace_key
            and str(row['scope']) == MemoryScope.REPO.value
        ):
            score += 1.0
        if bool(row['pinned']):
            score += 0.5
        return MemorySearchResult(
            id=str(row['id']),
            source='memory',
            score=score,
            snippet=clip(text, 320),
            workspace_key=str(row['workspace_key']),
            created_at=str(row['created_at']),
            scope=MemoryScope(str(row['scope'])),
            kind=MemoryKind(str(row['kind'])),
            pinned=bool(row['pinned']),
        )

    def _search_result_from_chat_row(
        self,
        row: sqlite3.Row,
        query_terms: list[str],
    ) -> MemorySearchResult:
        base_score = -float(row['rank'])
        snippet = self._render_chat_text(str(row['user_prompt']), str(row['assistant_reply']))
        score = (
            base_score
            + 0.05
            + _recency_boost(str(row['updated_at']))
            + _overlap_boost(snippet, query_terms)
        )
        return MemorySearchResult(
            id=str(row['id']),
            source='chat',
            score=score,
            snippet=clip(snippet, 360),
            workspace_key=str(row['workspace_key']),
            created_at=str(row['created_at']),
            session_id=str(row['session_id']),
        )

    def _render_chat_text(self, user_prompt: str, assistant_reply: str) -> str:
        return f'User: {user_prompt}\nAssistant: {assistant_reply}'
