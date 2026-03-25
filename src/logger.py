import logging
import os
import sys
from collections import deque


NEXUS_CONFIGURE_LOGGING = int(os.getenv("NEXUS_CONFIGURE_LOGGING", "1"))
NEXUS_LOGGING_LEVEL = os.getenv("NEXUS_LOGGING_LEVEL", "DEBUG")

_FORMAT = "%(levelname)s %(asctime)s %(filename)s:%(lineno)d] %(message)s"
_DATE_FORMAT = "%m-%d %H:%M:%S"

_LEVEL_COLORS = {
    "DEBUG":    "\033[36m",    # cyan
    "INFO":     "\033[32m",    # green
    "WARNING":  "\033[33m",    # yellow
    "ERROR":    "\033[31m",    # red
    "CRITICAL": "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Copy to avoid mutating the shared LogRecord seen by other handlers
        copy = logging.makeLogRecord(record.__dict__)
        color = _LEVEL_COLORS.get(record.levelname, "")
        copy.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(copy)


def _build_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ColorFormatter(fmt=_FORMAT, datefmt=_DATE_FORMAT))
    return handler



def init_logger(name: str) -> logging.Logger:
    """Return a named logger with Nexus formatting applied once."""
    log = logging.getLogger(name)
    if NEXUS_CONFIGURE_LOGGING and not log.handlers:
        log.setLevel(NEXUS_LOGGING_LEVEL)
        log.addHandler(_build_handler())
        log.propagate = False
    return log


# Module-level global logger
logger = init_logger("nexus")


class _StackHandler(logging.Handler):
    """Captures formatted log lines into an in-memory deque."""

    def __init__(self, maxlen: int | None = None) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATE_FORMAT))
        self._stack: deque[str] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        self._stack.append(self.format(record))

    def dump(self) -> list[str]:
        return list(self._stack)

    def clear(self) -> None:
        self._stack.clear()


class StackLogger:
    """Logger that accumulates records in memory alongside normal output.

    Useful for agent SOP generation — the full execution log is available
    as a plain list of strings via ``dump()``.

    Can be used as a context manager; the stack is cleared on entry and
    the final log is returned on exit.

    Example::

        stack = StackLogger("coding-agent")
        stack.info("Starting feature exploration")
        ...
        history = stack.dump()   # pass to SOP() or store for review
        stack.clear()

        # or as a context manager
        with StackLogger("coding-agent") as (stack, get_history):
            stack.info("Working...")
        print(get_history())
    """

    def __init__(self, name: str, maxlen: int | None = None) -> None:
        self._logger = init_logger(name)
        self._handler = _StackHandler(maxlen=maxlen)
        self._logger.addHandler(self._handler)


    def debug(self, msg: str, *args, **kwargs) -> None:
        self._logger.debug(msg, *args, **kwargs)


    def info(self, msg: str, *args, **kwargs) -> None:
        self._logger.info(msg, *args, **kwargs)

        
    def warning(self, msg: str, *args, **kwargs) -> None:
        self._logger.warning(msg, *args, **kwargs)


    def error(self, msg: str, *args, **kwargs) -> None:
        self._logger.error(msg, *args, **kwargs)


    def critical(self, msg: str, *args, **kwargs) -> None:
        self._logger.critical(msg, *args, **kwargs)


    def dump(self) -> list[str]:
        """Return all accumulated log lines as formatted strings."""
        return self._handler.dump()
    

    def clear(self) -> None:
        """Discard all accumulated log lines."""
        self._handler.clear()


    def __enter__(self):
        self.clear()
        return self, self.dump
    

    def __exit__(self, *_) -> None:
        self._logger.removeHandler(self._handler)
