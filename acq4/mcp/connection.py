"""Client-side teleprox connection manager for the acq4-mcp server.

Holds teleprox clients (one per thread, per address, via RPCClient.get_client) and
tracks the active ACQ4 target, so the teleprox port can be supplied -- or changed --
mid-session without restarting the MCP server. This module has no dependency on the
`mcp` SDK, so the connection logic is unit-testable on its own.
"""

from teleprox import RPCClient

DEFAULT_HOST = "127.0.0.1"
HOST_MODULE = "acq4.mcp.host"


class NotConnectedError(RuntimeError):
    """Raised when a tool needs an ACQ4 target but none is active and none was given."""


class ConnectionManager:
    """Resolve, cache, and call the ACQ4-side host module over teleprox."""

    def __init__(self, host_module_provider=None):
        # host_module_provider(host, port) -> proxy to acq4.mcp.host on that target.
        # Injectable so the manager's resolution/delegation logic is testable without
        # a live teleprox connection.
        self._active = None  # (host, port) or None
        self._host_module_provider = host_module_provider or self._teleprox_host_module

    @property
    def active_address(self):
        """Return the active target as "host:port", or None if not connected."""
        if self._active is None:
            return None
        return f"{self._active[0]}:{self._active[1]}"

    def _teleprox_host_module(self, host, port):
        """Return a proxy to acq4.mcp.host on the given target via teleprox."""
        client = RPCClient.get_client(f"tcp://{host}:{port}")
        return client._import(HOST_MODULE)

    def _host_module(self, host, port):
        """Return the host-module proxy for the given target."""
        return self._host_module_provider(host, port)

    def _resolve(self, host, port):
        """Return (host, port) from an explicit override or the active connection."""
        if port is None:
            if self._active is None:
                raise NotConnectedError(
                    "No active ACQ4 connection. Call connect_acq4(port) first, or pass a port."
                )
            return self._active
        return (host or DEFAULT_HOST, port)

    def connect(self, port, host=DEFAULT_HOST):
        """Connect to an ACQ4 target, make it active, and return its instance_info."""
        info = dict(self._host_module(host, port).instance_info(_return_type="value"))
        self._active = (host, port)
        info["host"] = host
        info["port"] = port
        return info

    def execute(self, code, gui_thread=False, timeout=30.0, port=None, host=None):
        """Run *code* on the resolved target and return the host result dict."""
        host, port = self._resolve(host, port)
        return self._host_module(host, port).execute(
            code, gui_thread, _return_type="value", _timeout=timeout
        )

    def list_devices(self, port=None, host=None):
        """Return the target's device-name -> class-name mapping."""
        host, port = self._resolve(host, port)
        return self._host_module(host, port).list_devices(_return_type="value")

    def list_modules(self, port=None, host=None):
        """Return the target's loaded and defined module names."""
        host, port = self._resolve(host, port)
        return self._host_module(host, port).list_modules(_return_type="value")

    def manager_state(self, port=None, host=None):
        """Return the target's Manager storage/config summary."""
        host, port = self._resolve(host, port)
        return self._host_module(host, port).manager_state(_return_type="value")

    def get_log(self, lines=50, port=None, host=None):
        """Return the tail of the target's ACQ4 log file."""
        host, port = self._resolve(host, port)
        return self._host_module(host, port).get_log(lines, _return_type="value")
