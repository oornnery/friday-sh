"""REPL debug logging helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rich.logging import RichHandler
from rich.traceback import Traceback

from friday.cli.output import console

__all__ = ['format_debug_status', 'print_debug_traceback', 'set_debug_logging']

_LOGGER_NAMES = ('friday', 'pydantic_ai', 'openai', 'httpx', 'httpcore')


@dataclass(slots=True)
class _DebugState:
    enabled: bool = False
    handler: logging.Handler | None = None
    root_level: int = logging.WARNING
    logger_levels: dict[str, int] = field(default_factory=dict)

_STATE = _DebugState()


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
