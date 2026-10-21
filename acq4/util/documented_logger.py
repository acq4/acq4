"""A logger class whose logging calls accept ``docs=[...]``.

acq4/__init__.py installs it before any acq4 logger is created.
"""

import logging


class DocumentedLogger(logging.Logger):
    """A Logger whose logging calls accept a ``docs`` keyword.

    ``docs`` is a documentation path, or a list of them, relative to the ACQ4 docs
    root (e.g. ``"userGuide/configuration.html"``), as in HelpfulException. It is
    stored as ``record.docs``; acq4.util.LogWindow.DocumentedLogModel shows it as
    links, and other handlers format the record as usual.
    """

    def _log(
        self,
        level,
        msg,
        args,
        exc_info=None,
        extra=None,
        stack_info=False,
        stacklevel=1,
        docs=None,
    ):
        if docs is not None:
            extra = {**(extra or {}), 'docs': docs}
        # One extra stack level, so findCaller reports the call site, not this override.
        super()._log(
            level,
            msg,
            args,
            exc_info=exc_info,
            extra=extra,
            stack_info=stack_info,
            stacklevel=stacklevel + 1,
        )


def install_documented_logger() -> None:
    """Make DocumentedLogger the class of every logger created after this call.

    Loggers that already exist keep their class and still reject ``docs=``.
    """
    logging.setLoggerClass(DocumentedLogger)
