"""Spawn and track SSH tunnels so a remote ACQ4 rig can be reached by local port.

Runs on the MCP-server (client) machine. Tunnels are `ssh -N -L` subprocesses we own,
so they can be torn down; targets rely on ~/.ssh/config for user/hostname/keys.
"""

import socket
import subprocess
import time
from dataclasses import dataclass


@dataclass
class Tunnel:
    target: str
    remote_port: int
    local_port: int
    process: object


def _free_local_port() -> int:
    """Return an unused local TCP port by binding to port 0 and reading it back."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if a TCP connection to host:port succeeds right now."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


class SSHTunnelManager:
    """Open, reuse, and close `ssh -N -L` tunnels keyed by (target, remote_port)."""

    def __init__(self, spawn=None, wait_timeout=10.0):
        # spawn(argv) -> process; injectable so tests need no real ssh.
        self._spawn = spawn or (lambda argv: subprocess.Popen(argv))
        self._wait_timeout = wait_timeout
        self._tunnels = {}  # (target, remote_port) -> Tunnel

    @property
    def active(self):
        """Live tunnels whose process is still running, keyed by (target, remote_port)."""
        for key, tun in list(self._tunnels.items()):
            if tun.process.poll() is not None:
                del self._tunnels[key]
        return dict(self._tunnels)

    def open(self, target, remote_port, local_port=None):
        """Open (or reuse) a tunnel to target:remote_port; return the local port."""
        key = (target, remote_port)
        existing = self.active.get(key)
        if existing is not None:
            return existing.local_port

        if local_port is None:
            local_port = _free_local_port()
        argv = [
            "ssh",
            "-N",
            "-L",
            f"{local_port}:127.0.0.1:{remote_port}",
            target,
        ]
        proc = self._spawn(argv)

        deadline = time.monotonic() + self._wait_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"ssh tunnel to {target}:{remote_port} exited before it was ready"
                )
            if _port_open(local_port):
                self._tunnels[key] = Tunnel(target, remote_port, local_port, proc)
                return local_port
            time.sleep(0.1)

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise RuntimeError(
            f"ssh tunnel to {target}:{remote_port} did not open on local port "
            f"{local_port} within {self._wait_timeout}s"
        )

    def close(self, target=None):
        """Terminate the tunnel(s) for one target, or all tunnels; return closed targets."""
        closed = []
        for key, tun in list(self._tunnels.items()):
            if target is None or key[0] == target:
                tun.process.terminate()
                try:
                    tun.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                closed.append(key[0])
                del self._tunnels[key]
        return closed
