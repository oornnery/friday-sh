"""REPL completions for slash commands and @ file references."""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from friday.cli.catalog import REPL_COMMANDS, resource_subcommands
from friday.cli.resources import list_mode_names
from friday.infra.config import FridaySettings
from friday.infra.memory import SQLiteMemoryStore


class FridayCompleter(Completer):
    """Completer that handles slash commands and @ file paths."""

    def __init__(
        self,
        workspace_root: Path,
        session_dir: Path | None = None,
        memory_db_path: Path | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.session_dir = session_dir
        self.memory_db_path = memory_db_path

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> list[Completion]:
        text = document.text_before_cursor

        if text.startswith('/'):
            return list(self._complete_slash(text))

        at_pos = text.rfind('@')
        if at_pos >= 0:
            partial = text[at_pos + 1 :]
            return list(self._complete_files(partial, len(partial)))

        return []

    def _complete_slash(self, text: str) -> list[Completion]:
        parts = text.split()

        if len(parts) <= 1 and not text.endswith(' '):
            partial = parts[0] if parts else ''
            return self._matching_completions(REPL_COMMANDS, partial)

        command = parts[0]
        if command not in REPL_COMMANDS:
            return []

        current = '' if text.endswith(' ') else parts[-1]
        subcommands = resource_subcommands(command.removeprefix('/'))
        if not subcommands:
            return []

        if len(parts) == 1 or (len(parts) == 2 and not text.endswith(' ')):
            items = {subcommand: '' for subcommand in subcommands}
            return self._matching_completions(items, current)

        if command == '/modes' and parts[1] == 'set':
            items = {mode: '' for mode in list_mode_names()}
            return self._matching_completions(items, current)

        if command == '/settings' and parts[1] == 'get':
            items = {name: '' for name in FridaySettings.model_fields}
            return self._matching_completions(items, current)

        if command == '/sessions' and parts[1] in {'set', 'delete'}:
            items = {session_id: 'saved session' for session_id in self._session_ids()}
            return self._matching_completions(items, current)

        if command == '/memories' and parts[1] in {'get', 'delete'}:
            items = {memory_id: 'shared memory' for memory_id in self._memory_ids()}
            return self._matching_completions(items, current)

        if command == '/debug':
            items = {'on': '', 'off': '', 'status': ''}
            return self._matching_completions(items, current)

        return []

    def _matching_completions(
        self,
        items: dict[str, str],
        partial: str,
    ) -> list[Completion]:
        completions: list[Completion] = []
        for value, description in items.items():
            if not value.startswith(partial):
                continue
            completions.append(
                Completion(
                    value,
                    start_position=-len(partial),
                    display_meta=description,
                )
            )
        return completions

    def _session_ids(self) -> list[str]:
        if self.session_dir is None or not self.session_dir.exists():
            return []
        return sorted(path.stem for path in self.session_dir.glob('*.json'))

    def _memory_ids(self) -> list[str]:
        if self.memory_db_path is None:
            return []
        store = SQLiteMemoryStore(self.memory_db_path)
        records = store.list_memories(
            workspace_key=self.workspace_root.resolve().as_posix(),
            limit=30,
        )
        return [record.id for record in records]

    def _complete_files(self, partial: str, word_len: int) -> list[Completion]:
        if '/' in partial:
            parent_str, prefix = partial.rsplit('/', 1)
            search_dir = self.workspace_root / parent_str
        else:
            parent_str = ''
            prefix = partial
            search_dir = self.workspace_root

        if not search_dir.is_dir():
            return []

        completions: list[Completion] = []
        try:
            for entry in sorted(search_dir.iterdir()):
                name = entry.name
                if name.startswith('.'):
                    continue
                if prefix and not name.lower().startswith(prefix.lower()):
                    continue

                rel = f'{parent_str}/{name}' if parent_str else name
                display = f'{name}/' if entry.is_dir() else name
                if entry.is_dir():
                    rel += '/'

                completions.append(
                    Completion(
                        rel,
                        start_position=-word_len,
                        display=display,
                        display_meta='dir' if entry.is_dir() else '',
                    )
                )
        except PermissionError:
            return []

        return completions[:50]
