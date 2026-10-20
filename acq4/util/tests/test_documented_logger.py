"""Tests that ``docs=[...]`` works on every acq4 logger and every kind of handler.
Covers the class install and its ordering, plain/JSON formatting, and the log window.
"""

from __future__ import annotations

import inspect
import io
import json
import logging
import os
import subprocess
import sys
import textwrap

import pytest

import acq4

from acq4.logging_config import StringAwareJsonFormatter, get_logger
from acq4.util.documented_logger import DocumentedLogger

DOCS = ["userGuide/configuration.html"]


@pytest.fixture
def logger_and_stream():
    """A throwaway acq4 logger wired to a plain StreamHandler, with a plain Formatter.

    Loggers are process-global, so this one is handed back with exactly the handlers
    it started with; a test that adds its own does not leak into the next.
    """
    logger = get_logger("tests.documented_logger_probe")
    original_handlers = logger.handlers[:]
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter('%(levelname)s %(name)s %(message)s'))
    logger.addHandler(handler)
    try:
        yield logger, stream, handler
    finally:
        logger.handlers[:] = original_handlers
        logger.propagate = True


def test_get_logger_returns_a_documented_logger():
    assert isinstance(get_logger("tests.some_module"), DocumentedLogger)


def test_docs_reaches_a_plain_handler_and_formats_normally(logger_and_stream):
    """A handler that has never heard of docs formats the record exactly as usual."""
    logger, stream, _handler = logger_and_stream

    logger.warning("Ignored unknown option 'frobnicate'", docs=DOCS)

    assert stream.getvalue() == (
        "WARNING acq4.tests.documented_logger_probe Ignored unknown option 'frobnicate'\n"
    )


def test_docs_arrives_on_the_record(logger_and_stream):
    logger, _stream, _handler = logger_and_stream
    seen = []
    logger.addHandler(_Collector(seen))

    logger.warning("some fault", docs=DOCS)

    assert seen[0].docs == DOCS


def test_a_call_without_docs_leaves_no_docs_attribute(logger_and_stream):
    """Only calls that ask for documentation get the attribute; nothing else grows one."""
    logger, _stream, _handler = logger_and_stream
    seen = []
    logger.addHandler(_Collector(seen))

    logger.warning("some fault")

    assert not hasattr(seen[0], 'docs')


def test_docs_survives_the_json_formatter_the_log_file_uses(logger_and_stream):
    """The log file's JSON formatter serialises docs alongside everything else."""
    logger, stream, handler = logger_and_stream
    handler.setFormatter(
        StringAwareJsonFormatter(reserved_attrs=[], rename_fields={"levelno": "level"})
    )

    logger.error("some fault", docs=DOCS)

    assert json.loads(stream.getvalue())['docs'] == DOCS


def test_extra_and_docs_both_land_on_the_record(logger_and_stream):
    """docs is merged into extra rather than replacing it."""
    logger, _stream, _handler = logger_and_stream
    seen = []
    logger.addHandler(_Collector(seen))

    logger.warning("some fault", extra={'deviceName': 'Clamp1'}, docs=DOCS)

    assert seen[0].deviceName == 'Clamp1'
    assert seen[0].docs == DOCS


class TestTheRecordStillPointsAtTheCallSite:
    """findCaller counts frames, and DocumentedLogger._log adds one.

    Without the matching stacklevel adjustment every record in ACQ4 would name
    documented_logger.py as its source, and the log window's code links -- which
    open the file at record.pathname:record.lineno -- would all open this class.
    """

    def test_a_call_with_docs(self, logger_and_stream):
        logger, _stream, _handler = logger_and_stream
        seen = []
        logger.addHandler(_Collector(seen))

        line = inspect.currentframe().f_lineno + 1
        logger.warning("some fault", docs=DOCS)

        assert seen[0].pathname == __file__
        assert seen[0].lineno == line
        assert seen[0].funcName == 'test_a_call_with_docs'

    def test_a_call_without_docs(self, logger_and_stream):
        logger, _stream, _handler = logger_and_stream
        seen = []
        logger.addHandler(_Collector(seen))

        line = inspect.currentframe().f_lineno + 1
        logger.warning("some fault")

        assert seen[0].pathname == __file__
        assert seen[0].lineno == line
        assert seen[0].funcName == 'test_a_call_without_docs'

    def test_an_explicit_stacklevel_still_counts_from_the_caller(self, logger_and_stream):
        logger, _stream, _handler = logger_and_stream
        seen = []
        logger.addHandler(_Collector(seen))

        def helper():
            logger.warning("some fault", stacklevel=2, docs=DOCS)

        line = inspect.currentframe().f_lineno + 1
        helper()

        assert seen[0].lineno == line


def test_every_acq4_logger_exists_under_the_documented_class():
    """The install has to beat every ``getLogger`` call in the package to the punch.

    A logger keeps the class it was created with, so an acq4 module that asks for
    its logger before acq4/__init__.py installs the class would be left with a
    stock Logger that still rejects docs=. Import the heaviest chain acq4 has, in
    a fresh interpreter, and check that none came out stock.
    """
    code = textwrap.dedent(
        """
        import logging
        import acq4
        import acq4.Manager  # noqa: F401  -- pulls in Qt, devices, the util package
        from acq4.util.documented_logger import DocumentedLogger

        print('ACQ4:' + acq4.__file__)
        stock = sorted(
            name
            for name, logger in logging.Logger.manager.loggerDict.items()
            if (name == 'acq4' or name.startswith('acq4.'))
            and isinstance(logger, logging.Logger)
            and not isinstance(logger, DocumentedLogger)
        )
        print('STOCK:' + repr(stock))
        """
    )
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=300
    )
    assert result.returncode == 0, result.stderr
    # Make sure the fresh interpreter read this checkout and not an installed copy,
    # or the result below would say nothing about the code under test.
    imported = [ln for ln in result.stdout.splitlines() if ln.startswith('ACQ4:')]
    assert imported == ['ACQ4:' + acq4.__file__], result.stdout
    reported = [ln for ln in result.stdout.splitlines() if ln.startswith('STOCK:')]
    assert reported == ['STOCK:[]'], result.stdout


@pytest.fixture(scope="module")
def qapp():
    """A QApplication is required to instantiate the Qt-backed log model."""
    from acq4.util import Qt

    return Qt.QApplication.instance() or Qt.QApplication([])


def test_the_log_window_turns_docs_into_documentation_links(logger_and_stream, qapp):
    """The record a docs= call produces reaches DocumentedLogModel as it expects.

    This is the other end of the feature: the model routes the record's ``docs``
    attribute to _create_docs_children and builds a clickable 'Documentation'
    branch from it.
    """
    from teleprox.log.logviewer.log_model import LogModel

    from acq4.util.LogWindow import DocumentedLogModel

    logger, _stream, _handler = logger_and_stream
    seen = []
    logger.addHandler(_Collector(seen))
    logger.error("Error in ACQ4 configuration", docs=DOCS)
    record = seen[0]

    model = DocumentedLogModel()
    handler = model._get_attribute_handler('docs')
    assert handler != LogModel._get_attribute_handler(model, 'docs')

    children = handler(record, 'docs', record.docs)

    docs_item = children[0][0]
    assert docs_item.text() == "Documentation (docs)"
    links = [docs_item.child(i, 0).text() for i in range(docs_item.rowCount())]
    assert links == [f"📖 {DOCS[0]}"]


class _Collector(logging.Handler):
    """Keeps the LogRecord objects it is handed, so tests can inspect their attributes."""

    def __init__(self, sink):
        super().__init__()
        self.sink = sink

    def emit(self, record):
        self.sink.append(record)
