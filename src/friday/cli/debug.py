"""REPL debug logging helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler
from rich.traceback import Traceback

from friday.cli.output import console

__all__ = [
    'format_debug_status',
    'print_debug_traceback',
    'set_debug_logging',
    'setup_file_logging',
]

_LOGGER_NAMES = ('friday', 'pydantic_ai', 'openai', 'httpx', 'httpcore')

_FILE_LOG_FMT = '%(asctime)s %(levelname)-8s %(name)s: %(message)s'
_FILE_LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'


@dataclass(slots=True)
class _DebugState:
    enabled: bool = False
    handler: logging.Handler | None = None
    file_handler: logging.Handler | None = None
    root_level: int = logging.WARNING
    logger_levels: dict[str, int] = field(default_factory=dict)


_STATE = _DebugState()


def setup_file_logging(log_file: Path) -> None:
    """Always-on file logging. Independent of /debug toggle.

    Writes DEBUG-level logs for friday.* and INFO for third-party
    loggers to a rotating file (5MB, 3 backups).
    """
    if _STATE.file_handler is not None:
        return

    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8',
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(_FILE_LOG_FMT, datefmt=_FILE_LOG_DATEFMT))

    # friday.* gets DEBUG, everything else stays at their current level
    friday_logger = logging.getLogger('friday')
    friday_logger.addHandler(handler)
    friday_logger.setLevel(logging.DEBUG)

    _STATE.file_handler = handler
    logging.getLogger('friday.cli.debug').debug('file logging started: %s', log_file)


def set_debug_logging(enabled: bool) -> bool:
    """Enable or disable verbose logging for the interactive REPL."""
    if enabled == _STATE.enabled:
        return _STATE.enabled

    root_logger = logging.getLogger()
    if enabled:
        handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            show_time=False,
            show_path=False,
            markup=True,
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))

        _STATE.root_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)
        _STATE.handler = handler

        for name in _LOGGER_NAMES:
            logger = logging.getLogger(name)
            _STATE.logger_levels[name] = logger.level
            logger.setLevel(logging.DEBUG)

        _STATE.enabled = True
        logging.getLogger(__name__).debug('repl debug logging enabled')
        return True

    logging.getLogger(__name__).debug('repl debug logging disabled')
    if _STATE.handler is not None:
        root_logger.removeHandler(_STATE.handler)
        _STATE.handler.close()
        _STATE.handler = None
    root_logger.setLevel(_STATE.root_level)
    for name, level in _STATE.logger_levels.items():
        logging.getLogger(name).setLevel(level)
    _STATE.enabled = False
    return False


def print_debug_traceback(exc: BaseException) -> None:
    """Print a full traceback to the console."""
    tb = Traceback.from_exception(
        type(exc),
        exc,
        exc.__traceback__,
        show_locals=True,
    )
    console.print(tb)


def format_debug_status(enabled: bool) -> str:
    """Render a short status string for `/debug`."""
    return 'on' if enabled else 'off'
