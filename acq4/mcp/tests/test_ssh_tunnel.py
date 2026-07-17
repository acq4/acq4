"""Tests for acq4.mcp.ssh_tunnel: spawning and tracking SSH tunnels for remote rigs.

The ssh spawn is injected so free-port selection, idempotent reuse, and teardown are
covered without launching real ssh.
"""

import pytest

from acq4.mcp import ssh_tunnel
from acq4.mcp.ssh_tunnel import SSHTunnelManager


class _FakeProc:
    def __init__(self, argv):
        self.argv = argv
        self.terminated = False

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.terminated = True
        return 0


@pytest.fixture
def spawned():
    return []


@pytest.fixture
def manager(spawned, monkeypatch):
    # Tunnel always "ready" so open() does not block on a real port.
    monkeypatch.setattr(ssh_tunnel, "_port_open", lambda port, host="127.0.0.1": True)

    def fake_spawn(argv):
        proc = _FakeProc(argv)
        spawned.append(proc)
        return proc

    return SSHTunnelManager(spawn=fake_spawn)


def test_open_spawns_ssh_and_returns_local_port(manager, spawned):
    local = manager.open("minirig", 40104, local_port=45000)
    assert local == 45000
    argv = spawned[0].argv
    assert argv[0] == "ssh"
    assert "-N" in argv
    assert "-L" in argv
    assert "45000:127.0.0.1:40104" in argv
    assert argv[-1] == "minirig"
    assert (
        argv[-2] == "--"
    )  # guards a target starting with "-" from being parsed as an option


def test_open_picks_free_port_when_unspecified(manager, monkeypatch):
    monkeypatch.setattr(ssh_tunnel, "_free_local_port", lambda: 49999)
    assert manager.open("minirig", 40104) == 49999


def test_open_is_idempotent_per_target_and_port(manager, spawned):
    first = manager.open("minirig", 40104, local_port=45000)
    second = manager.open("minirig", 40104, local_port=45000)
    assert first == second
    assert len(spawned) == 1  # not spawned twice


def test_open_reraises_when_tunnel_never_opens(spawned, monkeypatch):
    monkeypatch.setattr(ssh_tunnel, "_port_open", lambda port, host="127.0.0.1": False)
    mgr = SSHTunnelManager(spawn=lambda argv: _FakeProc(argv), wait_timeout=0.05)
    with pytest.raises(RuntimeError, match="tunnel"):
        mgr.open("minirig", 40104, local_port=45000)


def test_close_terminates_tracked_tunnel(manager, spawned):
    manager.open("minirig", 40104, local_port=45000)
    closed = manager.close("minirig")
    assert closed == ["minirig"]
    assert spawned[0].terminated is True
    assert manager.active == {}


def test_close_all_terminates_every_tunnel(manager, spawned):
    manager.open("minirig", 40104, local_port=45000)
    manager.open("bigrig", 40105, local_port=45001)
    manager.close()
    assert all(p.terminated for p in spawned)
    assert manager.active == {}


def test_open_reraises_when_ssh_exits_immediately(monkeypatch):
    # ssh dies right after spawn: open() must raise, not hang.
    monkeypatch.setattr(ssh_tunnel, "_port_open", lambda port, host="127.0.0.1": False)

    class _DeadProc:
        def __init__(self, argv):
            self.argv = argv

        def poll(self):
            return 1  # already exited

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 1

    mgr = SSHTunnelManager(spawn=lambda argv: _DeadProc(argv), wait_timeout=1.0)
    with pytest.raises(RuntimeError, match="exited"):
        mgr.open("minirig", 40104, local_port=45000)
