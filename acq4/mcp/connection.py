"""Client-side teleprox connection manager for the acq4-mcp server.

Holds teleprox clients (one per thread, per address, via RPCClient.get_client) and
tracks the active ACQ4 target, so the teleprox port can be supplied -- or changed --
mid-session without restarting the MCP server. This module has no dependency on the
`mcp` SDK, so the connection logic is unit-testable on its own.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from teleprox import RPCClient

DEFAULT_HOST = "127.0.0.1"
HOST_MODULE = "acq4.mcp.host"


class NotConnectedError(RuntimeError):
    """Raised when a tool needs an ACQ4 target but none is active and none was given."""


class ConnectionManager:
    """Resolve, cache, and call the ACQ4-side host module over teleprox."""

    def __init__(self, host_module_provider=None, serialize=True):
        # host_module_provider(host, port) -> proxy to acq4.mcp.host on that target.
        # Injectable so the manager's resolution/delegation logic is testable without
        # a live teleprox connection.
        self._active = None  # (host, port) or None
        self._host_module_provider = host_module_provider or self._teleprox_host_module

        # teleprox/zmq sockets are not thread-safe: two threads touching one socket
        # corrupt its multipart framing (recoverable) or trip a libzmq assertion
        # (fatal). Route every teleprox operation through a single dedicated worker
        # thread so exactly one client socket is ever used, and only by that thread.
        self._executor = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="acq4-mcp")
            if serialize
            else None
        )
        self._local = threading.local()

    def _run(self, fn, *args, **kwargs):
        """Run *fn* on the dedicated worker thread and block for its result.

        Reentrant calls (already on the worker) run inline to avoid self-deadlock on
        the single worker.
        """
        if self._executor is None or getattr(self._local, "in_worker", False):
            return fn(*args, **kwargs)

        def wrapped():
            self._local.in_worker = True
            try:
                return fn(*args, **kwargs)
            finally:
                self._local.in_worker = False

        return self._executor.submit(wrapped).result()

    def close(self):
        """Shut down the worker thread."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)

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
        return self._run(self._connect, port, host)

    def _connect(self, port, host):
        info = dict(self._host_module(host, port).instance_info(_return_type="value"))
        self._active = (host, port)
        info["host"] = host
        info["port"] = port
        return info

    def execute(self, code, gui_thread=False, timeout=30.0, port=None, host=None):
        """Run *code* on the resolved target and return the host result dict."""
        return self._run(self._execute, code, gui_thread, timeout, port, host)

    def _execute(self, code, gui_thread, timeout, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).execute(
            code, gui_thread, _return_type="value", _timeout=timeout
        )

    def list_devices(self, port=None, host=None):
        """Return the target's device-name -> class-name mapping."""
        return self._run(self._list_devices, port, host)

    def _list_devices(self, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).list_devices(_return_type="value")

    def list_modules(self, port=None, host=None):
        """Return the target's loaded and defined module names."""
        return self._run(self._list_modules, port, host)

    def _list_modules(self, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).list_modules(_return_type="value")

    def manager_state(self, port=None, host=None):
        """Return the target's Manager storage/config summary."""
        return self._run(self._manager_state, port, host)

    def _manager_state(self, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).manager_state(_return_type="value")

    def get_log(self, lines=50, port=None, host=None):
        """Return the tail of the target's ACQ4 log file."""
        return self._run(self._get_log, lines, port, host)

    def _get_log(self, lines, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).get_log(lines, _return_type="value")

    def reset_namespace(self, port=None, host=None):
        """Clear the target's persistent exec namespace."""
        return self._run(self._reset_namespace, port, host)

    def _reset_namespace(self, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).reset_namespace(_return_type="value")

    def profile_functions(self, seconds=10.0, top=15, port=None, host=None):
        """Profile function hot-spots on the target for `seconds`."""
        return self._run(self._profile_functions, seconds, top, port, host)

    def _profile_functions(self, seconds, top, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).profile_functions(
            seconds, top, _return_type="value", _timeout=seconds + 15
        )

    def memory_snapshot(self, name=None, top=15, port=None, host=None):
        """Take a memory snapshot on the target and summarize it."""
        return self._run(self._memory_snapshot, name, top, port, host)

    def _memory_snapshot(self, name, top, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).memory_snapshot(
            name, top, _return_type="value", _timeout=60.0
        )

    def profile_qt_events(self, seconds=10.0, top=15, port=None, host=None):
        """Profile the Qt event loop on the target for `seconds`."""
        return self._run(self._profile_qt_events, seconds, top, port, host)

    def _profile_qt_events(self, seconds, top, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).profile_qt_events(
            seconds, top, _return_type="value", _timeout=seconds + 15
        )

    def health_series(self, seconds=10.0, interval=1.0, port=None, host=None):
        """Collect a resource health time-series from the target."""
        return self._run(self._health_series, seconds, interval, port, host)

    def _health_series(self, seconds, interval, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).health_series(
            seconds, interval, _return_type="value", _timeout=seconds + 15
        )
