import logging
import logging.handlers
import sys

from pythonjsonlogger.json import JsonFormatter
from acq4.util.LogWindow import get_log_window


def setup_logging(
    log_file_path: str = "app.log",
    log_window: bool = True,
    root_level: int = logging.INFO,
    console_level: int = logging.WARNING
) -> None:
    """
    Set up the complete logging configuration.

    Args:
        log_file_path: Path to the log file
        root_level: Root logger level
    """
    root_logger = logging.getLogger("acq4")
    root_logger.setLevel(root_level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # 1. Console handler (stderr, WARNING and above)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. File handler (all messages, JSON format)
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    json_formatter = JsonFormatter(
        reserved_attrs=[],  # Include all the fields
        rename_fields={"levelno": "level"},
        json_ensure_ascii=False,
        exc_info_as_array=True,
    )
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)

    # 3. GUI Log Window handler (all messages)
    if log_window:
        log_window = get_log_window()
        log_window.handler.setLevel(logging.DEBUG)
        root_logger.addHandler(log_window.handler)


def get_logger(name: str = "acq4") -> logging.Logger:
    """
    Get a logger by name. Use __name__ for module-level loggers. Ensures the name starts with
    'acq4.'.
    """
    if name != "acq4" and not name.startswith("acq4."):
        name = f"acq4.{name}"
    return logging.getLogger(name)


def set_logger_level(logger_name: str, level: int) -> None:
    """
    Dynamically change a specific logger's level.

    Args:
        logger_name: Name of the logger (e.g., 'acq4.devices.camera')
        level: New level (logging.DEBUG, logging.INFO, 25, etc.)
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    print(f"Set {logger_name} to {logging.getLevelName(level)}")


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
