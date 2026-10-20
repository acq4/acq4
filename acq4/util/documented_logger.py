"""The logger class that lets any logging call carry ``docs=[...]``.
Installed from acq4/__init__.py, ahead of every logger acq4 creates.
"""

import logging


class DocumentedLogger(logging.Logger):
    """A Logger whose logging calls accept a ``docs`` keyword.

    ``docs`` is a documentation path, or a list of them, relative to the ACQ4 docs
    root -- ``"userGuide/configuration.html"`` and the like. It rides on the record
    as ``record.docs``, which DocumentedLogModel turns into clickable links in the
    log window. To a handler that knows nothing about it the record is an ordinary
    one carrying an extra attribute, so stderr, the JSON log file and pytest's
    capture format it unchanged.

    It is the same spelling HelpfulException uses for the same thing, so a fault
    can point at its documentation whether it is raised or only logged.
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
        # findCaller counts frames out from Logger._log, and this override sits one
        # frame inside it, so every call needs one more level to report the call
        # site rather than this file.
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
    """Make DocumentedLogger the class of every logger created from here on.

    logging fixes a logger's class when the logger is first created and never
    revisits it, so a logger that exists already keeps the stock class and would
    still reject ``docs=``. acq4/__init__.py calls this before it imports anything,
    which is the earliest point any acq4 logger can be asked for.
    """
    logging.setLoggerClass(DocumentedLogger)
