import logging
import logging.handlers
import sys

from pythonjsonlogger.json import JsonFormatter

from acq4.util.LogWindow import get_log_window, get_error_dialog
from teleprox.log import LogServer

log_server: LogServer | None = None


class StringAwareJsonFormatter(JsonFormatter):
    """
    Custom JSON formatter that handles both real exc_info tuples and pre-formatted strings.
    """

    def formatException(self, ei):
        """
        Format exception info, but pass through if it's already a string.
        """
        # If it's already a string or nested strings, return as is
        if isinstance(ei, str) or (
            isinstance(ei, (list, tuple)) and all(isinstance(i, str) for i in ei)
        ):
            return ei

        # Otherwise, format normally
        return super().formatException(ei)

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        # Handle exception info - could be real exc_info or pre-formatted string
        if record.exc_info:
            log_record['exc_info'] = self.formatException(record.exc_info)
        elif hasattr(record, 'exc_text') and record.exc_text:
            # Handle case where only the exception text is known
            log_record['exc_info'] = record.exc_text
        else:
            log_record['exc_info'] = None


class HistoricLogRecord(logging.LogRecord):
    """
    A LogRecord subclass that can be instantiated from a dictionary of attributes and preservers them.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.created = kwargs.get('created', self.created)
        self.msecs = kwargs.get('msecs', self.msecs)
        self.relativeCreated = kwargs.get('relativeCreated', self.relativeCreated)
        self.thread = kwargs.get('thread', self.thread)
        self.threadName = kwargs.get('threadName', self.threadName)
        self.process = kwargs.get('process', self.process)
        self.processName = kwargs.get('processName', self.processName)


def setup_logging(
    log_file_path: str = "app.log",
    gui: bool = True,
    acq4_level: int = logging.DEBUG,
    console_level: int = logging.WARNING,
) -> logging.FileHandler:
    """
    Sets log levels and then creates or refreshes log handlers for a file, the console,
    and optionally the primary Log window and error popup. It also starts a teleprox
    LogServer as needed.

    Parameters
    ----------
    log_file_path: Path to the log file
    gui: Whether to connect to GUI log window and error dialog
    acq4_level: 'acq4' logger level
    console_level: Console handler level

    Returns
    -------
    The file handler (in case you want to fill the file in with old log records)
    """
    global log_server

    acq4_logger = logging.getLogger("acq4")
    acq4_logger.setLevel(acq4_level)

    # Clear any existing handlers
    acq4_logger.handlers.clear()

    # 1. Console handler (stderr, WARNING and above)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    acq4_logger.addHandler(console_handler)

    # 2. File handler (all messages, JSON format)
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    json_formatter = StringAwareJsonFormatter(
        reserved_attrs=[],  # Include all the fields
        rename_fields={"levelno": "level"},
        json_ensure_ascii=False,
        exc_info_as_array=True,
    )
    file_handler.setFormatter(json_formatter)
    acq4_logger.addHandler(file_handler)

    # 3. Teleprox
    if log_server is None:
        log_server = LogServer(acq4_logger)

    # 4. GUI Log Window handler (all messages)
    if gui:
        log_window = get_log_window()
        log_window.handler.setLevel(logging.DEBUG)
        acq4_logger.addHandler(log_window.handler)

        # 5. GUI error dialog handler (ERROR and above)
        error_dialog = get_error_dialog()
        error_dialog.handler.setLevel(logging.ERROR)
        acq4_logger.addHandler(error_dialog.handler)

    return file_handler


def get_logger(name: str = "acq4") -> logging.Logger:
    """
    Get a logger by name. Use __name__ for module-level loggers. Ensures the name starts with
    'acq4.'.
    """
    if name != "acq4" and not name.startswith("acq4."):
        name = f"acq4.{name}"
    return logging.getLogger(name)


def list_active_loggers() -> list:
    """Debug utility to see all active loggers and their levels."""
    loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
    loggers.append(logging.getLogger())  # root logger

    return [
        {
            "level": (logging.getLevelName(logger.level)),
            "effective": (logging.getLevelName(logger.getEffectiveLevel())),
            "name": (logger.name or 'root'),
            "logger": logger,
        }
        for logger in sorted(loggers, key=lambda x: x.name or '')
    ]
