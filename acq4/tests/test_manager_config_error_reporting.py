"""What the operator is told when a non-device configuration option is wrong.

``_loadConfig`` reports those faults from its own ``except:`` handler, so a handler
that cannot run leaves the real fault invisible at startup.
"""

from __future__ import annotations

import logging

import pytest

from acq4.Manager import Manager


@pytest.fixture
def man():
    """The slice of Manager that ``_loadConfig`` touches, with errors reported not raised.

    Manager.__init__ builds a whole application -- singleton guard, log window,
    devices -- so bypass it and populate only what the config chain reads, the way
    acq4/tests/test_manager_panic_config.py does.
    """
    man = Manager.__new__(Manager)
    man.exitOnError = False
    man.disableAllDevs = False
    man.disableDevs = []
    man.definedModules = {}
    return man


def test_a_bad_compression_option_reports_the_real_fault(man, caplog):
    """The ValueError the option actually caused reaches the log, with its message.

    This is the regression for ``logger.exception(..., docs=[...])`` raising out of
    the handler: when it does, the operator sees a TypeError about a logging kwarg,
    or nothing at all, instead of being told which option they got wrong.
    """
    with caplog.at_level(logging.DEBUG, logger="acq4"):
        man._loadConfig({'defaultCompression': 'nonsense'})

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    record = errors[0]
    assert "Error in ACQ4 configuration" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError
    assert "defaultCompression" in str(record.exc_info[1])
    assert "nonsense" in str(record.exc_info[1])


def test_the_config_error_carries_its_documentation_link(man, caplog):
    """The ``docs=`` link the call site passes arrives on the record."""
    with caplog.at_level(logging.DEBUG, logger="acq4"):
        man._loadConfig({'defaultCompression': 'nonsense'})

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].docs == ["userGuide/configuration.html"]
