"""Tests for acq4.mcp's teleprox server discovery and on-demand start.
No real port is ever bound; RPCServer is patched throughout.
"""

import logging
from unittest import mock

import pytest

from acq4 import mcp


@pytest.fixture(autouse=True)
def clean_state():
    mcp._reset_teleprox_state_for_test()
    yield
    mcp._reset_teleprox_state_for_test()


def test_no_server_means_no_address():
    assert mcp.get_teleprox_address() is None


def test_set_address_decodes_bytes():
    mcp.set_teleprox_address(b"tcp://127.0.0.1:5555")
    assert mcp.get_teleprox_address() == "tcp://127.0.0.1:5555"


def test_ensure_returns_existing_without_starting_or_asking():
    mcp.set_teleprox_address("tcp://127.0.0.1:5555")
    confirm = mock.Mock(return_value=True)
    with mock.patch("teleprox.RPCServer") as server:
        assert mcp.ensure_teleprox_server(confirm=confirm) == "tcp://127.0.0.1:5555"
    server.assert_not_called()
    confirm.assert_not_called()


def test_ensure_starts_server_when_confirmed():
    with mock.patch("teleprox.RPCServer") as server:
        server.return_value.address = b"tcp://127.0.0.1:6666"
        addr = mcp.ensure_teleprox_server(confirm=lambda: True)
    assert addr == "tcp://127.0.0.1:6666"
    server.assert_called_once_with("tcp://127.0.0.1:*")
    assert mcp.get_teleprox_address() == "tcp://127.0.0.1:6666"


def test_ensure_is_idempotent():
    with mock.patch("teleprox.RPCServer") as server:
        server.return_value.address = b"tcp://127.0.0.1:6666"
        first = mcp.ensure_teleprox_server(confirm=lambda: True)
        second = mcp.ensure_teleprox_server(confirm=lambda: True)
    assert first == second
    assert server.call_count == 1


def test_decline_starts_nothing_and_does_not_reask():
    confirm = mock.Mock(return_value=False)
    with mock.patch("teleprox.RPCServer") as server:
        assert mcp.ensure_teleprox_server(confirm=confirm) is None
        assert mcp.ensure_teleprox_server(confirm=confirm) is None
    server.assert_not_called()
    confirm.assert_called_once()


def test_start_is_logged_at_warning_with_address(caplog):
    with caplog.at_level(logging.WARNING, logger="acq4"):
        with mock.patch("teleprox.RPCServer") as server:
            server.return_value.address = b"tcp://127.0.0.1:6666"
            mcp.ensure_teleprox_server(confirm=lambda: True)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("tcp://127.0.0.1:6666" in r.getMessage() for r in warnings)
