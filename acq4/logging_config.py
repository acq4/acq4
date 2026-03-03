import contextlib
import json
import logging
import os
import sys

from pythonjsonlogger.json import JsonFormatter

from acq4.util.LogWindow import get_log_window, get_error_dialog
from teleprox.log import LogServer

log_server: LogServer | None = None
log_handlers = []
log_file_handler: logging.FileHandler | None = None

def __reload__(old):
    global log_server, log_handlers
    log_server = old.get('log_server', None)
    log_handlers = old.get('_handlers', [])


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
        if isinstance(kwargs.get('args'), list):
            kwargs['args'] = tuple(kwargs['args'])
        super().__init__(**kwargs)
        self.created = kwargs.get('created', self.created)
        self.msecs = kwargs.get('msecs', self.msecs)
        self.relativeCreated = kwargs.get('relativeCreated', self.relativeCreated)
        self.thread = kwargs.get('thread', self.thread)
        self.threadName = kwargs.get('threadName', self.threadName)
        self.process = kwargs.get('process', self.process)
        self.processName = kwargs.get('processName', self.processName)


def load_historic_log_records(log_file):
    records = []
    for line in log_file.readlines():
        records.append(HistoricLogRecord(**(json.loads(line))))
    return records


def setup_logging(
    log_file: str,
    gui: bool = True,
    root_level: int = logging.DEBUG,
    acq4_level: int = logging.DEBUG,
    console_level: int = logging.WARNING,
    is_temp_file: bool = False,
):
    """
    Sets log levels and then creates or refreshes log handlers for a file, the console,
    and optionally the primary Log window and error popup. It also starts a teleprox
    LogServer as needed.

    Parameters
    ----------
    log_file: str
        Path to the log file
    gui: Whether to connect to GUI log window and error dialog
    acq4_level: 'acq4' logger level
    console_level: Console handler level
    is_temp_file: If True, this log file is temporary and should be migrated to the main log file later.
    """
    global log_server
    global log_file_handler

    # clear out old handlers
    root_logger = logging.getLogger()
    for handler in log_handlers:
        root_logger.removeHandler(handler)
        with contextlib.suppress(Exception):
            handler.close()
    log_handlers.clear()

    # set logging levels
    acq4_logger = logging.getLogger("acq4")
    acq4_logger.setLevel(acq4_level)
    root_logger.setLevel(root_level)

    # set up new file handler
    set_log_file(log_file, is_temp_file=is_temp_file)

    # Add console handler (prints to stderr, WARNING and above)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    log_handlers.append(console_handler)

    # Start teleprox log server (receive log records from other processes)
    if log_server is None:
        log_server = LogServer(acq4_logger)

    # GUI Log Window handler (all messages)
    if gui:
        log_window = get_log_window()
        log_window.handler.setLevel(logging.DEBUG)
        root_logger.addHandler(log_window.handler)
        log_handlers.append(log_window.handler)

        # GUI error dialog handler (ERROR and above)
        error_dialog = get_error_dialog()
        error_dialog.handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_dialog.handler)
        log_handlers.append(error_dialog.handler)


def set_log_file(log_file: str | None, is_temp_file: bool = False) -> None:
    """Set the log file path for the file handler. 
    If a file handler already exists, it will be closed and removed before creating a new one.
    
    If the previous log file was a temporary file created during early initialization, 
    its contents will be read and rewritten to the new log file handler to preserve all log records.
    """
    global log_file_handler

    root_logger = logging.getLogger()

    # remove old handler if it exists
    old_log_file = None
    if log_file_handler is not None:
        if log_file_handler.is_temp_file:
            old_log_file = log_file_handler.baseFilename
        root_logger.removeHandler(log_file_handler)
        log_file_handler.close()
        log_file_handler = None

    # copy old log file to new location
    if old_log_file is not None and old_log_file != log_file:
        oldlog = open(old_log_file, 'rb').read()
        with open(log_file, 'ab') as f:
            f.write(oldlog)

    # Add new log file handler (all messages, JSON format)
    log_file_handler = logging.FileHandler(log_file)
    log_file_handler.setLevel(logging.DEBUG)
    log_file_handler.is_temp_file = is_temp_file
    json_formatter = StringAwareJsonFormatter(
        reserved_attrs=[],  # Include all the fields
        rename_fields={"levelno": "level"},
        json_ensure_ascii=False,
        exc_info_as_array=True,
    )
    log_file_handler.setFormatter(json_formatter)
    root_logger.addHandler(log_file_handler)

    # replaced by the copy operation above
    # if old_log_file is not None and old_log_file != log_file:
    #     rewrite_log_from_temp_file(old_log_file)


def rewrite_log_from_temp_file(temp_file_path: str) -> None:
    """Read the temporary log file created during early initialization and rewrite its contents to the current log file handler, 
    preserving all record attributes. 
    This should be called after the main logging configuration is set up and a new log file handler is created."""
    logger = logging.getLogger()

    if log_file_handler is None:
        raise RuntimeError("Log file handler is not set up. Cannot rewrite log from temp file.")
    try:
        with open(temp_file_path, 'r') as f:
            for line_num, line in enumerate(f, start=1):
                if not line.strip():
                    continue  # skip blank lines
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    preview = line[:200].replace('\r', '\\r').replace('\n', '\\n')
                    logger.warning(
                        f"Skipping corrupted temporary log entry in {temp_file_path!r} at line {line_num}: "
                        f"{preview!r}\nError was: {exc}"
                    )
                else:
                    log_file_handler.emit(HistoricLogRecord(**record))
    finally:
        os.remove(temp_file_path)
        
    # log_win = get_log_window()
    # with open(self._logFile.name(), 'r') as f:
    #     for i, line in enumerate(f):
    #         log_win.new_record(HistoricLogRecord(**(json.loads(line))), sort=False)
    #         if i % 20 == 0:
    #             Qt.QApplication.processEvents()
    # log_win.ensure_chronological_sorting()


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
