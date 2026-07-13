"""acq4-mcp: an MCP stdio server that executes code on a running ACQ4 over teleprox.

Thin glue over acq4.mcp.connection.ConnectionManager. Only this module imports the
optional `mcp` SDK (the ``acq4[mcp]`` extra), and it does so lazily inside
build_server(); acq4.mcp.host and acq4.mcp.connection have no such dependency, so they
import on every ACQ4 install. The teleprox port is supplied at runtime via the
connect_acq4 tool (or a per-call port argument), so it can change without restarting.
"""

import argparse
import json
from typing import Optional

from acq4.mcp.connection import ConnectionManager, NotConnectedError

# One connection manager for the life of the server process; the active ACQ4 target is
# chosen and can be re-pointed at runtime through the connect_acq4 tool.
_connection = ConnectionManager()


def _format_execute(result: dict) -> str:
    """Render a host.execute result dict as readable text for the model."""
    sections = []
    if result.get("stdout"):
        sections.append(f"stdout:\n{result['stdout'].rstrip()}")
    if result.get("stderr"):
        sections.append(f"stderr:\n{result['stderr'].rstrip()}")
    if result.get("result") is not None:
        sections.append(f"result: {result['result']}")
    if result.get("traceback"):
        sections.append(f"Traceback:\n{result['traceback'].rstrip()}")
    if not sections:
        return "(no output)"
    return "\n\n".join(sections)


def build_server():
    """Construct and return the FastMCP server with all tools registered.

    The `mcp` SDK is imported here (not at module import) so acq4.mcp.server can be
    imported for its pure helpers even where the `mcp` extra is not installed.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("acq4")

    @server.tool()
    def connect_acq4(port: int, host: str = "127.0.0.1") -> str:
        """Connect to a running ACQ4's teleprox server and make it the active target.

        ACQ4 must have been started with `--teleprox <port>` (or `--teleprox` for a
        random port, printed at startup as "Teleprox server listening on ..."). The
        port can change between ACQ4 restarts; call this again with a new port to
        re-point without restarting the MCP server. Returns an identity/sanity summary
        (version, hostname, base dir, device count) so you can confirm the right rig.

        host defaults to 127.0.0.1 (ACQ4 binds localhost); a remote rig needs an SSH
        tunnel to that port.
        """
        return json.dumps(_connection.connect(port, host), indent=2, default=str)

    @server.tool()
    def execute_code(
        code: str,
        gui_thread: bool = False,
        timeout: float = 30.0,
        port: Optional[int] = None,
        host: Optional[str] = None,
    ) -> str:
        """Execute arbitrary Python inside the running ACQ4 process and return its output.

        The code runs in a persistent namespace shared across calls (variables persist;
        call reset_namespace to clear it). The namespace is seeded with `man` (the ACQ4
        Manager, via getManager()) and `acq4`. Captured stdout/stderr, the value of a
        trailing expression (repr), and any traceback are returned.

        SAFETY -- read this before mutating anything: inspect freely, but obtain
        EXPLICIT USER APPROVAL before executing anything that changes running state or
        moves hardware: stage/pipette moves, pressure changes, clamp mode changes,
        starting tasks or acquisitions, or writing config/data. When unsure whether an
        action mutates, treat it as mutating and ask first.

        gui_thread selects where the code runs -- choosing wrong can crash or freeze
        ACQ4:
        * gui_thread=False (default): run off the GUI thread. Use for anything blocking
          or long-running -- device moves, .wait(), acquisitions, sleeps, patch state
          changes. Running these on the GUI thread would FREEZE or DEADLOCK ACQ4.
        * gui_thread=True: marshal onto the Qt GUI thread and block until it returns.
          Use ONLY for fast, non-blocking access to Qt widgets/objects or GUI state.
          Touching Qt objects off the GUI thread risks a SEGFAULT, but never run
          blocking work here.

        port/host optionally override the active connection for this one call.
        """
        try:
            result = _connection.execute(
                code, gui_thread=gui_thread, timeout=timeout, port=port, host=host
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"
        return _format_execute(result)

    @server.tool()
    def reset_namespace(port: Optional[int] = None, host: Optional[str] = None) -> str:
        """Clear the persistent execute_code namespace on the ACQ4 side.

        execute_code shares one long-lived namespace across calls (variables persist).
        Call this to discard all of that accumulated state and start fresh; `man` and
        `acq4` are re-seeded on the next execute_code call.
        """
        try:
            return json.dumps(
                _connection.reset_namespace(port=port, host=host), indent=2, default=str
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"

    @server.tool()
    def list_devices(port: Optional[int] = None, host: Optional[str] = None) -> str:
        """Return the ACQ4 devices as a name -> device-class mapping (read-only)."""
        try:
            return json.dumps(
                _connection.list_devices(port=port, host=host), indent=2, default=str
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"

    @server.tool()
    def list_modules(port: Optional[int] = None, host: Optional[str] = None) -> str:
        """Return loaded and configured-but-unloaded ACQ4 module names (read-only)."""
        try:
            return json.dumps(
                _connection.list_modules(port=port, host=host), indent=2, default=str
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"

    @server.tool()
    def manager_state(port: Optional[int] = None, host: Optional[str] = None) -> str:
        """Return ACQ4 Manager storage dirs, device count, and config keys (read-only)."""
        try:
            return json.dumps(
                _connection.manager_state(port=port, host=host), indent=2, default=str
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"

    @server.tool()
    def get_log(
        lines: int = 50, port: Optional[int] = None, host: Optional[str] = None
    ) -> str:
        """Return the tail of the ACQ4 log file (read-only)."""
        try:
            log = _connection.get_log(lines=lines, port=port, host=host)
        except NotConnectedError as exc:
            return f"Not connected: {exc}"
        return f"{log.get('path')}\n\n{log.get('text', '')}"

    return server


def main():
    """Console-script entry point: run the acq4-mcp stdio server."""
    parser = argparse.ArgumentParser(
        description="MCP server for a running ACQ4 (via teleprox)."
    )
    parser.parse_args()
    build_server().run()


if __name__ == "__main__":
    main()
