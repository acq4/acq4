"""Tests for acq4.mcp.connection: the client-side teleprox connection manager.

The bulk are deterministic unit tests using an injected fake host-module provider, so
resolution, active-target tracking, port overrides, and delegation are covered without a
live socket. A single module-scoped live test exercises the real teleprox round-trip.
"""

import pytest

from acq4.mcp.connection import ConnectionManager, NotConnectedError


class _FakeHostModule:
    """Stand-in for the remote acq4.mcp.host proxy; records the target it was built for.

    Methods accept and ignore teleprox call kwargs (_return_type, _timeout) the way the
    real ObjectProxy would, and record them so tests can assert they were passed.
    """

    def __init__(self, recorder, host, port):
        self.recorder = recorder
        self.host = host
        self.port = port

    def instance_info(self, **kw):
        self.recorder.append(("instance_info", self.host, self.port, kw))
        return {"hostname": "fakerig", "has_manager": False, "device_count": None}

    def execute(self, code, gui_thread=False, **kw):
        self.recorder.append(("execute", self.host, self.port, code, gui_thread, kw))
        return {
            "stdout": "",
            "stderr": "",
            "result": repr(eval(code)),
            "traceback": None,
        }

    def list_devices(self, **kw):
        self.recorder.append(("list_devices", self.host, self.port, kw))
        return {"cam": "MockCamera"}

    def reset_namespace(self, **kw):
        self.recorder.append(("reset_namespace", self.host, self.port, kw))
        return {"reset": True}

    def profile_functions(self, seconds, top, **kw):
        self.recorder.append(
            ("profile_functions", self.host, self.port, seconds, top, kw)
        )
        return {"top_functions": []}


@pytest.fixture
def recorder():
    return []


@pytest.fixture
def manager(recorder):
    return ConnectionManager(
        host_module_provider=lambda h, p: _FakeHostModule(recorder, h, p)
    )


def test_execute_without_connection_raises(manager):
    with pytest.raises(NotConnectedError):
        manager.execute("1 + 1")


def test_connect_returns_info_and_sets_active(manager):
    info = manager.connect(5000)
    assert info["host"] == "127.0.0.1"
    assert info["port"] == 5000
    assert info["hostname"] == "fakerig"
    assert manager.active_address == "127.0.0.1:5000"


def test_execute_uses_active_target(manager, recorder):
    manager.connect(5000)
    result = manager.execute("21 * 2")
    assert result["result"] == "42"
    execute_calls = [c for c in recorder if c[0] == "execute"]
    assert execute_calls[0][1:3] == ("127.0.0.1", 5000)


def test_explicit_port_overrides_without_prior_connect(manager, recorder):
    result = manager.execute("'ok'", port=6000, host="10.0.0.5")
    assert result["result"] == "'ok'"
    assert recorder[-1][1:3] == ("10.0.0.5", 6000)


def test_reconnect_updates_active_target(manager, recorder):
    manager.connect(5000)
    manager.connect(6000)
    assert manager.active_address == "127.0.0.1:6000"
    manager.execute("1 + 1")
    assert recorder[-1][1:3] == ("127.0.0.1", 6000)


def test_execute_passes_timeout_to_remote_call(manager, recorder):
    manager.connect(5000)
    manager.execute("1 + 1", timeout=99.0)
    assert recorder[-1][5]["_timeout"] == 99.0


def test_list_devices_delegates_to_target(manager, recorder):
    manager.connect(5000)
    devices = manager.list_devices()
    assert devices == {"cam": "MockCamera"}
    assert recorder[-1][0] == "list_devices"


def test_reset_namespace_delegates_to_target(manager, recorder):
    manager.connect(5000)
    assert manager.reset_namespace() == {"reset": True}
    assert recorder[-1][0] == "reset_namespace"
    assert recorder[-1][1:3] == ("127.0.0.1", 5000)


def test_profile_functions_delegates_with_timeout(manager, recorder):
    manager.connect(5000)
    manager.profile_functions(seconds=5.0, top=3)
    call = recorder[-1]
    assert call[0] == "profile_functions"
    assert call[1:3] == ("127.0.0.1", 5000)
    assert call[3] == 5.0 and call[4] == 3
    assert call[5]["_timeout"] >= 20.0  # seconds + margin


def test_all_teleprox_access_serialized_onto_one_thread():
    """Every teleprox call must run on a single dedicated thread, even under concurrent
    callers, so one zmq client socket is never touched by two threads at once.
    """
    import threading

    idents = []
    idents_lock = threading.Lock()

    class _IdentModule:
        def __init__(self, host, port):
            pass

        def _record(self):
            with idents_lock:
                idents.append(threading.get_ident())

        def instance_info(self, **kw):
            self._record()
            return {"has_manager": False}

        def execute(self, code, gui_thread=False, **kw):
            self._record()
            return {"result": None}

    cm = ConnectionManager(host_module_provider=lambda h, p: _IdentModule(h, p))
    cm.connect(5000)

    callers = [threading.Thread(target=lambda: cm.execute("1")) for _ in range(6)]
    for t in callers:
        t.start()
    for t in callers:
        t.join()

    worker_idents = set(idents)
    assert (
        len(worker_idents) == 1
    ), f"teleprox access spread across threads: {worker_idents}"
    assert worker_idents != {
        threading.get_ident()
    }, "should run on a dedicated worker, not the caller"


# ---------------------------------------------------------------------------
# Live round-trip over a real teleprox child process (the same separate-process
# model the MCP server uses in production, and teleprox's own reliable test pattern).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def child_process():
    import teleprox

    proc = teleprox.start_process(name="acq4-mcp-test")
    yield proc
    proc.stop()


def _address_port(address):
    return int(str(address).rsplit(":", 1)[1].rstrip("'\""))


def test_live_connect_and_execute(child_process):
    port = _address_port(child_process.client.address)
    cm = ConnectionManager()
    info = cm.connect(port)
    assert info["port"] == port
    assert info["has_manager"] is False  # no Manager in the bare child process
    result = cm.execute("21 * 2")
    assert result["result"] == "42"
    assert result["traceback"] is None
