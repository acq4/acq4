"""MCP integration for ACQ4: execute code and inspect a running instance over teleprox.

This package must import cleanly on every ACQ4 install; the optional `mcp` SDK is
only imported by `acq4.mcp.server` (the stdio MCP process), never at package import.
"""

import logging

logger = logging.getLogger("acq4")

# Teleprox lifecycle. A teleprox RPC server is what lets an MCP client reach into
# this process. It may be started at launch by `--teleprox`, or on demand by a
# feature that needs it (see acq4/util/claude_debug.py).
#
# CONTRACT: starting this server opens a loopback port that permits arbitrary code
# execution inside ACQ4 for the remainder of the session. teleprox's own docs state
# plainly that RPCServer is not a secure server. On-demand starts therefore go
# through a confirmation and are logged at WARNING.
_teleprox_server = None      # server this module started, if any
_teleprox_address = None     # address of whichever server is serving; str or None
_teleprox_declined = False   # operator said no; do not ask again this session


def set_teleprox_address(addr):
    """Record the address of a server started elsewhere (e.g. by ``--teleprox``)."""
    global _teleprox_address
    _teleprox_address = addr.decode() if isinstance(addr, bytes) else addr


def get_teleprox_address():
    """Return the address of the running teleprox server, or None if there is none."""
    return _teleprox_address


def ensure_teleprox_server(confirm=None):
    """Return a teleprox address, starting a server if none is running.

    Idempotent. Returns None if no server is running and *confirm* declines; the
    refusal is remembered for the session so the operator is asked only once.

    confirm : callable returning bool, or None
        Asked before opening a port. None means do not start one.
    """
    global _teleprox_server, _teleprox_declined
    if _teleprox_address is not None:
        return _teleprox_address
    if _teleprox_declined or confirm is None:
        return None
    if not confirm():
        _teleprox_declined = True
        return None

    import teleprox

    _teleprox_server = teleprox.RPCServer("tcp://127.0.0.1:*")
    set_teleprox_address(_teleprox_server.address)
    logger.warning(
        "Started teleprox server on %s for AI-assisted debugging. This port allows "
        "code execution in this ACQ4 process until it exits.",
        _teleprox_address,
    )
    return _teleprox_address


def _reset_teleprox_state_for_test():
    """Clear module-level teleprox state. For tests only."""
    global _teleprox_server, _teleprox_address, _teleprox_declined
    _teleprox_server = None
    _teleprox_address = None
    _teleprox_declined = False
