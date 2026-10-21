"""Tests that Manager._loadConfig logs the real fault for a bad non-device option."""

from __future__ import annotations

import logging

import pytest

from acq4.Manager import Manager


@pytest.fixture
def man():
    """A Manager with only the attributes ``_loadConfig`` uses, and exitOnError off.

    Bypasses Manager.__init__, which builds the whole application.
    """
    man = Manager.__new__(Manager)
    man.exitOnError = False
    man.disableAllDevs = False
    man.disableDevs = []
    man.definedModules = {}
    return man


def test_a_bad_compression_option_reports_the_real_fault(man, caplog):
    """A bad defaultCompression value logs its ValueError, not a logging TypeError."""
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
