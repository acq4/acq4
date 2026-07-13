# acq4-mcp Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three capabilities to the `acq4-mcp` server — a persistent exec namespace, profiling tools that drive ACQ4's live Profiler window, and one-call SSH-tunnel connection.

**Architecture:** Extend the existing three-layer MCP (`host.py` runs inside ACQ4; `connection.py` is the client-side teleprox manager; `server.py` is the FastMCP glue). Feature 2 also needs a companion refactor in the `rtprofile` package (public headless collection methods), cloned locally and installed editable.

**Tech Stack:** Python 3.12, teleprox RPC, FastMCP (`mcp` SDK, optional extra), pyqtgraph/Qt, guppy3, psutil, rtprofile, pytest (+ pytest-qt for the rtprofile widget tests).

## Global Constraints

- Python interpreter for all commands: `/home/martin/.miniforge3/envs/acq4-gl/bin/python` (the `acq4-gl` env).
- Run tests with `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest`.
- `acq4/mcp/host.py` and `acq4/mcp/connection.py` MUST NOT import the `mcp` SDK, and MUST import cleanly on an ACQ4 install where `rtprofile`/`guppy` may be absent — so import `rtprofile`/`guppy` **lazily inside functions**, never at module top.
- Style: `black` formatting; match surrounding code; every new file starts with a 2-line docstring describing what it does.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- Commits authored `Martin Chase (claude) <outofculture@gmail.com>`; conventional-commit messages; footer `🤖 Generated with [Claude Code](https://claude.ai/code)` then `Co-Authored-By: WOZCODE <contact@withwoz.com>`. Never use `--no-verify`.
- Branch: `feat/acq4-mcp` (acq4 repo). rtprofile work lands in a clone at `/home/martin/src/acq4/rtprofile` on its own branch + upstream PR.
- Threading rule (host): anything that touches Qt widgets/objects runs via `acq4.util.task.run_in_gui_thread`; timed profiling windows sleep **off** the GUI thread.

---

## Task ordering

Features 1 and 3 are self-contained and ship first. The rtprofile prerequisite (Task 6) precedes the Feature 2 host code (Tasks 7–11). Within Feature 2, pure helpers are tested with fabricated objects; the live Qt/Manager/guppy path is verified manually.

---

## FEATURE 1 — Persistent exec namespace

### Task 1: Persistent namespace + `reset_namespace` in host

**Files:**
- Modify: `acq4/mcp/host.py`
- Test: `acq4/mcp/tests/test_host.py`

**Interfaces:**
- Produces: `host._get_namespace() -> dict` (module-global, lazily built, reused); `host.reset_namespace() -> dict` returning `{"reset": True}`; `host.execute(code, gui_thread=False)` now execs against the shared namespace.
- Consumes: existing `host._build_namespace()`, `host._exec_and_capture()`.

- [ ] **Step 1: Write failing tests**

Add to `acq4/mcp/tests/test_host.py`:

```python
def test_execute_persists_variables_across_calls():
    host.reset_namespace()
    host.execute("persisted_value = 123")
    result = host.execute("persisted_value * 2")
    assert result["result"] == "246"


def test_reset_namespace_clears_state():
    host.execute("scratch = 'gone soon'")
    host.reset_namespace()
    result = host.execute("'scratch' in dir()")
    assert result["result"] == "False"


def test_reset_namespace_returns_confirmation():
    assert host.reset_namespace() == {"reset": True}


def test_namespace_reheals_man_once_manager_exists(monkeypatch):
    import acq4

    host.reset_namespace()
    # First build: no Manager yet -> man is None.
    monkeypatch.setattr(acq4, "getManager", lambda: (_ for _ in ()).throw(RuntimeError("none")))
    assert host.execute("man is None")["result"] == "True"
    host.execute("user_var = 7")  # user state that must survive the heal
    # Manager appears.
    sentinel = object()
    monkeypatch.setattr(acq4, "getManager", lambda: sentinel)
    assert host.execute("man is not None")["result"] == "True"
    assert host.execute("user_var")["result"] == "7"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host.py -k "persist or reset_namespace or reheals" -v`
Expected: FAIL with `AttributeError: module 'acq4.mcp.host' has no attribute 'reset_namespace'`.

- [ ] **Step 3: Implement**

In `acq4/mcp/host.py`, add after `_build_namespace()`:

```python
_PERSISTENT_NS = None


def _get_namespace() -> dict:
    """Return the process-global persistent exec namespace, building it on first use.

    State set by one execute() call is visible to the next. `man` is re-resolved when it
    was None (no Manager existed at build time) so it heals once a Manager appears,
    without disturbing user-defined variables. Call reset_namespace() to start clean.
    """
    global _PERSISTENT_NS
    if _PERSISTENT_NS is None:
        _PERSISTENT_NS = _build_namespace()
    if _PERSISTENT_NS.get("man") is None:
        import acq4

        try:
            _PERSISTENT_NS["man"] = acq4.getManager()
        except Exception:
            pass
    return _PERSISTENT_NS


def reset_namespace() -> dict:
    """Discard the persistent exec namespace so the next execute() starts fresh."""
    global _PERSISTENT_NS
    _PERSISTENT_NS = None
    return {"reset": True}
```

In `execute()`, replace `namespace = _build_namespace()` with `namespace = _get_namespace()`, and update the docstring line "A fresh namespace is built for every call (no state persists between calls)" to: "A single persistent namespace is shared across calls (state persists); call reset_namespace() to clear it."

- [ ] **Step 4: Run tests, verify pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host.py -v`
Expected: PASS (all, including the pre-existing tests — note `test_execute_seeds_man_as_none_without_manager` still passes because no Manager is monkeypatched there; add `host.reset_namespace()` as its first line so a leaked namespace from another test can't seed a real `man`).

Add `host.reset_namespace()` as the first line of the existing `test_execute_seeds_man_as_none_without_manager`, `test_execute_returns_last_expression_repr`, and `test_execute_seeds_acq4_module` tests to keep them isolated from persisted state.

- [ ] **Step 5: Commit**

```bash
git add acq4/mcp/host.py acq4/mcp/tests/test_host.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: persist exec namespace across acq4-mcp calls

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 2: `reset_namespace` connection delegator

**Files:**
- Modify: `acq4/mcp/connection.py`
- Test: `acq4/mcp/tests/test_connection.py`

**Interfaces:**
- Consumes: `host.reset_namespace()`.
- Produces: `ConnectionManager.reset_namespace(port=None, host=None) -> dict`.

- [ ] **Step 1: Write failing test**

Extend `_FakeHostModule` in `acq4/mcp/tests/test_connection.py` with:

```python
    def reset_namespace(self, **kw):
        self.recorder.append(("reset_namespace", self.host, self.port, kw))
        return {"reset": True}
```

Add:

```python
def test_reset_namespace_delegates_to_target(manager, recorder):
    manager.connect(5000)
    assert manager.reset_namespace() == {"reset": True}
    assert recorder[-1][0] == "reset_namespace"
    assert recorder[-1][1:3] == ("127.0.0.1", 5000)
```

- [ ] **Step 2: Run test, verify fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_connection.py -k reset_namespace -v`
Expected: FAIL with `AttributeError: 'ConnectionManager' object has no attribute 'reset_namespace'`.

- [ ] **Step 3: Implement**

In `acq4/mcp/connection.py`, after the `execute`/`_execute` pair add:

```python
    def reset_namespace(self, port=None, host=None):
        """Clear the target's persistent exec namespace."""
        return self._run(self._reset_namespace, port, host)

    def _reset_namespace(self, port, host):
        host, port = self._resolve(host, port)
        return self._host_module(host, port).reset_namespace(_return_type="value")
```

- [ ] **Step 4: Run test, verify pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_connection.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acq4/mcp/connection.py acq4/mcp/tests/test_connection.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add reset_namespace delegator to connection manager

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 3: `reset_namespace` MCP tool + docs

**Files:**
- Modify: `acq4/mcp/server.py`, `acq4/mcp/README.md`

**Interfaces:**
- Consumes: `ConnectionManager.reset_namespace`.
- Produces: MCP tool `reset_namespace(port=None, host=None) -> str`.

- [ ] **Step 1: Implement the tool**

In `acq4/mcp/server.py`, inside `build_server()` after the `execute_code` tool, add:

```python
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
```

Also update the `execute_code` tool docstring: change "The code runs in a fresh namespace (nothing persists between calls)" to "The code runs in a persistent namespace shared across calls (variables persist; call reset_namespace to clear it)".

- [ ] **Step 2: Verify the server still builds and registers the tool**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "from acq4.mcp.server import build_server; s = build_server(); import asyncio; print(sorted(t.name for t in asyncio.run(s.list_tools())))"`
Expected: output list includes `'reset_namespace'` alongside the existing tools.

- [ ] **Step 3: Update README**

In `acq4/mcp/README.md`, in the Tools table add a row:
`| `reset_namespace(port=None, host=None)` | Clear the persistent execute_code namespace (read-only-ish). |`
and change the paragraph "runs in a fresh namespace each call (nothing persists between calls)" to describe the persistent namespace + `reset_namespace`.

- [ ] **Step 4: Commit**

```bash
git add acq4/mcp/server.py acq4/mcp/README.md
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: expose reset_namespace MCP tool and document persistence

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

---

## FEATURE 3 — SSH-tunnel auto-connect

### Task 4: `SSHTunnelManager`

**Files:**
- Create: `acq4/mcp/ssh_tunnel.py`
- Test: `acq4/mcp/tests/test_ssh_tunnel.py`

**Interfaces:**
- Produces:
  - `ssh_tunnel.Tunnel` dataclass: `target: str`, `remote_port: int`, `local_port: int`, `process` (Popen-like with `.poll()`, `.terminate()`, `.wait()`).
  - `ssh_tunnel.SSHTunnelManager(spawn=None, wait_timeout=10.0)` where `spawn(argv: list[str]) -> process` is injectable (defaults to `subprocess.Popen`).
    - `open(target: str, remote_port: int, local_port: int | None = None) -> int` — returns the local port; idempotent per `(target, remote_port)`.
    - `close(target: str | None = None) -> list[str]` — terminate one target's tunnel(s) or all; returns closed targets.
    - `active` property -> `dict[tuple[str, int], Tunnel]`.
  - Module helper `_free_local_port() -> int`.
  - Readiness check `_port_open(port: int, host="127.0.0.1") -> bool`.

- [ ] **Step 1: Write failing tests**

Create `acq4/mcp/tests/test_ssh_tunnel.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_ssh_tunnel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acq4.mcp.ssh_tunnel'`.

- [ ] **Step 3: Implement**

Create `acq4/mcp/ssh_tunnel.py`:

```python
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
            "ssh", "-N",
            "-L", f"{local_port}:127.0.0.1:{remote_port}",
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
                except Exception:
                    pass
                closed.append(key[0])
                del self._tunnels[key]
        return closed
```

- [ ] **Step 4: Run tests, verify pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_ssh_tunnel.py -v`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
git add acq4/mcp/ssh_tunnel.py acq4/mcp/tests/test_ssh_tunnel.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add SSHTunnelManager for remote acq4 rigs

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 5: `connect_via_ssh` / `disconnect_ssh` MCP tools + docs

**Files:**
- Modify: `acq4/mcp/server.py`, `acq4/mcp/README.md`

**Interfaces:**
- Consumes: `SSHTunnelManager.open/close`, `ConnectionManager.connect`.
- Produces: MCP tools `connect_via_ssh(target, remote_port, local_port=None) -> str`, `disconnect_ssh(target=None) -> str`.

- [ ] **Step 1: Implement**

In `acq4/mcp/server.py`, at module level near `_connection`:

```python
from acq4.mcp.ssh_tunnel import SSHTunnelManager

_tunnels = SSHTunnelManager()
```

Inside `build_server()` after `connect_acq4`:

```python
    @server.tool()
    def connect_via_ssh(
        target: str, remote_port: int, local_port: Optional[int] = None
    ) -> str:
        """Open an SSH tunnel to a remote rig and connect to its ACQ4 in one step.

        Example: connect_via_ssh("minirig", 40104) for an ACQ4 started with
        `--teleprox 40104` on host `minirig`. `target` is anything ssh accepts — a
        ~/.ssh/config alias, `user@host`, etc. A free local port is chosen unless you
        pass local_port. Spawns `ssh -N -L <local>:127.0.0.1:<remote_port> <target>`,
        waits for it, then connect_acq4 on the local end. Returns the rig identity
        summary. Reuses an existing tunnel for the same target/port.
        """
        try:
            port = _tunnels.open(target, remote_port, local_port=local_port)
        except RuntimeError as exc:
            return f"SSH tunnel failed: {exc}"
        return json.dumps(_connection.connect(port), indent=2, default=str)

    @server.tool()
    def disconnect_ssh(target: Optional[str] = None) -> str:
        """Close the SSH tunnel for `target` (or all tunnels if omitted)."""
        closed = _tunnels.close(target)
        return json.dumps({"closed": closed}, indent=2)
```

- [ ] **Step 2: Verify the server builds and registers the tools**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "from acq4.mcp.server import build_server; import asyncio; print(sorted(t.name for t in asyncio.run(build_server().list_tools())))"`
Expected: list includes `'connect_via_ssh'` and `'disconnect_ssh'`.

- [ ] **Step 3: Update README**

In `acq4/mcp/README.md`, replace the "### Remote rigs" manual `ssh -L` instructions with the `connect_via_ssh("minirig", 40104)` workflow (note it relies on `~/.ssh/config`), and add both tools to the Tools table.

- [ ] **Step 4: Commit**

```bash
git add acq4/mcp/server.py acq4/mcp/README.md
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add connect_via_ssh and disconnect_ssh MCP tools

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

---

## FEATURE 2 — Profiling tools

### Task 6: rtprofile companion — public headless collection methods

**Repo:** `rtprofile` (clone of `github.com/campagnola/rtprofile`), NOT the acq4 repo.

**Files:**
- Modify: `rtprofile/function_profiler.py`, `rtprofile/memory_profiler.py`, `rtprofile/qt_profiler.py`
- Test: `rtprofile/tests/test_headless_api.py` (create)

**Interfaces (Produces, consumed by Task 7–10):**
- `FunctionProfiler.start_session(name=None, max_duration=None) -> None`; `FunctionProfiler.stop_session() -> ProfileResult`
- `MemoryProfiler.take_snapshot(name=None) -> MemorySnapshot`
- `QtEventProfiler.start_session(name=None, hold_receivers=False) -> None`; `QtEventProfiler.stop_session() -> QApplicationProfile`

- [ ] **Step 1: Clone and install editable**

```bash
git clone https://github.com/campagnola/rtprofile /home/martin/src/acq4/rtprofile
cd /home/martin/src/acq4/rtprofile
git checkout -b feat/headless-collection-api
/home/martin/.miniforge3/envs/acq4-gl/bin/pip install -e .
```
Verify: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "import rtprofile, os; print(os.path.realpath(rtprofile.__file__))"` prints a path under `/home/martin/src/acq4/rtprofile`.

- [ ] **Step 2: Write failing tests**

Create `/home/martin/src/acq4/rtprofile/tests/test_headless_api.py`:

```python
"""Tests for the headless collection API used by acq4-mcp to drive the profiler widgets.

Each profiler exposes public start_session/stop_session/take_snapshot methods that the UI
buttons also call, so data is collectable without simulating clicks.
"""

import time

import pyqtgraph as pg
import pytest


@pytest.fixture(scope="module")
def qapp():
    return pg.mkQApp()


def test_function_profiler_start_stop_session_returns_result(qapp):
    from rtprofile.function_profiler import FunctionProfiler, ProfileResult

    fp = FunctionProfiler(parent_widget=None)
    fp.start_session(name="unit")
    sum(range(1000))
    result = fp.stop_session()
    assert isinstance(result, ProfileResult)
    assert result in fp.profile_results
    assert result.name == "unit"


def test_memory_profiler_take_snapshot_returns_snapshot(qapp):
    guppy = pytest.importorskip("guppy")
    from rtprofile.memory_profiler import MemoryProfiler, MemorySnapshot

    mp = MemoryProfiler(parent_widget=None)
    snap = mp.take_snapshot(name="unit")
    assert isinstance(snap, MemorySnapshot)
    assert snap in mp.snapshots


def test_qt_profiler_requires_profiled_qapp_gracefully(qapp):
    # With a plain QApplication (no start_profile), start_session should raise a clear
    # error rather than AttributeError.
    from rtprofile.qt_profiler import QtEventProfiler

    qp = QtEventProfiler(parent_widget=None)
    if not hasattr(qapp, "start_profile"):
        with pytest.raises(RuntimeError):
            qp.start_session(name="unit")
```

- [ ] **Step 3: Run tests, verify fail**

Run: `cd /home/martin/src/acq4/rtprofile && /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest tests/test_headless_api.py -v`
Expected: FAIL with `AttributeError: 'FunctionProfiler' object has no attribute 'start_session'`.

- [ ] **Step 4: Implement — FunctionProfiler**

In `rtprofile/function_profiler.py`, add public methods on `FunctionProfiler` and refactor the button handlers to call them:

```python
    def start_session(self, name=None, max_duration=None):
        """Begin a profiling session headlessly (used by the Start button and by callers)."""
        if not self.python_version_ok:
            raise RuntimeError("Function profiling requires a newer Python")
        self._pending_name = name or f"NewProfile_{len(self.profile_results) + 1}"
        self.current_profiler = Profile(
            max_duration=max_duration if max_duration else None,
            finish_callback=lambda profile: self.profilerFinished.emit(),
        )
        self.current_profiler.start()
        self.is_profiling = True
        self.current_session_start = datetime.now()

    def stop_session(self):
        """Stop the current session, store the result, and return it."""
        if not self.is_profiling or self.current_profiler is None:
            return None
        self.current_profiler.stop()
        name = getattr(self, "_pending_name", None) or f"NewProfile_{len(self.profile_results) + 1}"
        result = ProfileResult(name, self.current_session_start, self.current_profiler)
        self.profile_results.append(result)
        self.is_profiling = False
        self.current_session_start = None
        self.current_profiler = None
        return result
```

Refactor `_startProfiling` to read the widgets and delegate, keeping button/UI updates:

```python
    def _startProfiling(self):
        """Begin a new profiling session"""
        max_duration_text = self.max_duration_edit.text().strip()
        max_duration = float(max_duration_text) if max_duration_text else 0
        self.start_session(
            name=self.session_name_edit.text() or None,
            max_duration=max_duration if max_duration > 0 else None,
        )
        self.start_stop_btn.setText("Stop Profiling")
        self.start_stop_btn.setStyleSheet("background-color: #ff4444;")
```

Refactor `_stopProfiling` to delegate then update UI:

```python
    def _stopProfiling(self):
        """End current profiling session and store results"""
        result = self.stop_session()
        if result is None:
            return
        self._addResultToList(result)
        self.start_stop_btn.setText("Start Profiling")
        self.start_stop_btn.setStyleSheet("")
        self.session_name_edit.setText(f"NewProfile_{len(self.profile_results) + 1}")
```

- [ ] **Step 5: Implement — MemoryProfiler**

In `rtprofile/memory_profiler.py` add:

```python
    def take_snapshot(self, name=None):
        """Capture a guppy heap snapshot headlessly, store it, and return it."""
        if not GUPPY_AVAILABLE:
            raise RuntimeError("Guppy3 not available. Install with: pip install guppy3")
        snapshot_name = name or f"Snapshot_{len(self.snapshots) + 1}"
        timestamp = datetime.now()
        try:
            snapshot = MemorySnapshot(snapshot_name, timestamp, self.hpy.heap())
        except Exception as e:
            snapshot = MemorySnapshot(snapshot_name, timestamp, error_message=str(e))
        self.snapshots.append(snapshot)
        return snapshot
```

Refactor `_takeSnapshot` to delegate then update UI:

```python
    def _takeSnapshot(self):
        """Take a memory snapshot using guppy"""
        if not GUPPY_AVAILABLE:
            return
        snapshot = self.take_snapshot(name=self.snapshot_name_edit.text() or None)
        self._addSnapshotToList(snapshot)
        self.snapshot_name_edit.setText(f"Snapshot_{len(self.snapshots) + 1}")
```

- [ ] **Step 6: Implement — QtEventProfiler**

In `rtprofile/qt_profiler.py` add:

```python
    def start_session(self, name=None, hold_receivers=False):
        """Start a Qt event profiling session headlessly."""
        app = Qt.QApplication.instance()
        if not hasattr(app, "start_profile"):
            raise RuntimeError(
                "Qt event profiling requires ACQ4 started with --qt-profile "
                "(ProfiledQApplication)."
            )
        name = name or f"Qt_Profile_{len(self.profile_results) + 1}"
        self.current_profile = app.start_profile(name, hold_receivers=hold_receivers)
        self.is_profiling = True

    def stop_session(self):
        """Stop the current Qt session, store it, and return it."""
        if self.current_profile is None:
            return None
        self.current_profile.stop()
        profile = self.current_profile
        self.profile_results.append(profile)
        self.is_profiling = False
        self.current_profile = None
        return profile
```

Refactor `_startProfiling`/`_stopProfiling` to delegate then do the button/list UI updates (read `session_name_edit`, `hold_receivers_checkbox` in `_startProfiling`; call `_addResultToList(profile)` in `_stopProfiling`).

- [ ] **Step 7: Run tests, verify pass**

Run: `cd /home/martin/src/acq4/rtprofile && /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest tests/test_headless_api.py -v`
Expected: PASS.

- [ ] **Step 8: Commit, push, PR (rtprofile repo)**

```bash
cd /home/martin/src/acq4/rtprofile
git add -A
git commit -m "feat: public headless start_session/stop_session/take_snapshot API"
git push -u origin feat/headless-collection-api
gh pr create --draft --title "Headless collection API for embedding" --body "Adds public start_session/stop_session/take_snapshot to the three profilers so external callers (acq4-mcp) can drive collection; button handlers now call these. 🧙 Built with WOZCODE"
```

### Task 7: host profiler-tabs locator

**Files:**
- Modify: `acq4/mcp/host.py`
- Test: manual (needs live Manager+Qt); no unit test.

**Interfaces:**
- Produces: `host._profiler_tabs()` — returns the live `rtprofile.profiler_tabs.ProfilerTabs`, loading the `Profiler` module via `man.loadModule("Profiler")` if not already loaded. Runs on the GUI thread internally.

- [ ] **Step 1: Implement**

In `acq4/mcp/host.py` add (lazy imports; no module-level rtprofile):

```python
def _profiler_tabs():
    """Return the live Profiler module's ProfilerTabs widget, loading it if needed.

    Loads the `Profiler` module (opening its window) when it is not already loaded, so
    profiling data collects into the same window the human sees. Must be called on the
    GUI thread.
    """
    man = _manager()
    for name in man.listModules():
        mod = man.getModule(name)
        if type(mod).__name__ == "Profiler" and hasattr(mod, "profiler_tabs"):
            return mod.profiler_tabs
    mod = man.loadModule("Profiler")
    return mod.profiler_tabs
```

- [ ] **Step 2: Manual verification note**

Against a running rig (documented in the PR description, not automated):
`execute_code("from acq4.mcp import host; type(host._profiler_tabs()).__name__", gui_thread=True)` should return `'ProfilerTabs'` and the Profiler window should appear.

- [ ] **Step 3: Commit**

```bash
git add acq4/mcp/host.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: locate-or-open Profiler window from acq4-mcp host

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 8: host function-profiling + pure top-N helper

**Files:**
- Modify: `acq4/mcp/host.py`
- Test: `acq4/mcp/tests/test_host_profiling.py` (create) — covers the pure helper only.

**Interfaces:**
- Produces:
  - `host._top_functions(function_lookup: dict, top: int = 15) -> list[dict]` — pure; each row `{"function", "filename", "lineno", "n_calls", "total_seconds"}`, sorted by `total_seconds` desc.
  - `host.profile_functions(seconds: float = 10.0, top: int = 15) -> dict`.
- Consumes: rtprofile `ProfileAnalyzer.build_function_lookup()` (keys are function_key tuples; values `{"calls": [CallRecord...]}`), `CallRecord.duration`, `CallRecord.display_name`/`filename`/`lineno`, `FunctionProfiler.start_session/stop_session` (Task 6).

**Note on function_key shape (from rtprofile):** for Python calls `(filename, lineno, display_name)`; for C calls `("c_call", qualname, module)`. `_top_functions` must handle both without importing rtprofile.

- [ ] **Step 1: Write failing test (pure helper)**

Create `acq4/mcp/tests/test_host_profiling.py`:

```python
"""Unit tests for the pure aggregation/formatting helpers behind acq4-mcp profiling.

The live Qt/Manager/guppy collection path is verified manually; these cover the
data-shaping helpers with fabricated inputs.
"""

from acq4.mcp import host


class _Call:
    def __init__(self, duration, display_name, filename, lineno):
        self.duration = duration
        self.display_name = display_name
        self.filename = filename
        self.lineno = lineno


def test_top_functions_sorts_by_total_time_desc():
    lookup = {
        ("a.py", 10, "slow"): {"calls": [_Call(0.5, "slow", "a.py", 10), _Call(0.5, "slow", "a.py", 10)]},
        ("b.py", 20, "fast"): {"calls": [_Call(0.01, "fast", "b.py", 20)]},
    }
    rows = host._top_functions(lookup, top=10)
    assert [r["function"] for r in rows] == ["slow", "fast"]
    assert rows[0]["n_calls"] == 2
    assert abs(rows[0]["total_seconds"] - 1.0) < 1e-9


def test_top_functions_truncates_to_top_n():
    lookup = {
        (f"f{i}.py", i, f"fn{i}"): {"calls": [_Call(float(i), f"fn{i}", f"f{i}.py", i)]}
        for i in range(1, 6)
    }
    rows = host._top_functions(lookup, top=2)
    assert len(rows) == 2
    assert rows[0]["function"] == "fn5"


def test_top_functions_handles_c_call_keys():
    lookup = {("c_call", "builtins.len", "builtins"): {"calls": [_Call(0.2, "len", "<builtin>", 0)]}}
    rows = host._top_functions(lookup, top=5)
    assert rows[0]["function"] == "len"
    assert rows[0]["total_seconds"] == 0.2
```

- [ ] **Step 2: Run test, verify fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host_profiling.py -v`
Expected: FAIL with `AttributeError: module 'acq4.mcp.host' has no attribute '_top_functions'`.

- [ ] **Step 3: Implement**

In `acq4/mcp/host.py` add:

```python
def _top_functions(function_lookup, top=15):
    """Rank functions in a ProfileAnalyzer lookup by summed call duration (desc).

    function_lookup maps a function_key to {"calls": [CallRecord, ...]}. Pure: takes only
    the lookup dict so it is testable without a live profile.
    """
    rows = []
    for calls in (data["calls"] for data in function_lookup.values()):
        durations = [c.duration for c in calls if c.duration is not None]
        if not durations:
            continue
        first = calls[0]
        rows.append(
            {
                "function": first.display_name,
                "filename": first.filename,
                "lineno": first.lineno,
                "n_calls": len(durations),
                "total_seconds": sum(durations),
            }
        )
    rows.sort(key=lambda r: r["total_seconds"], reverse=True)
    return rows[:top]


def profile_functions(seconds=10.0, top=15):
    """Profile all-thread function calls for `seconds`, return the hottest functions.

    Drives the live Profiler window's function profiler (opening it if needed), so the
    same call tree is visible to the human. Must run off the GUI thread (it sleeps for
    the profiling window); the start/stop touch the widget via run_in_gui_thread.
    """
    import time

    from acq4.util import task
    from rtprofile.profiler import ProfileAnalyzer

    tabs = task.run_in_gui_thread(_profiler_tabs)
    fp = tabs.function_profiler
    if not hasattr(fp, "start_session"):
        raise RuntimeError(
            "Installed rtprofile lacks the headless start_session API; update rtprofile."
        )
    task.run_in_gui_thread(fp.start_session, None, None)
    time.sleep(seconds)
    result = task.run_in_gui_thread(fp.stop_session)
    analyzer = ProfileAnalyzer(result.profile)
    return {
        "session": result.name,
        "duration_seconds": result.profile_duration,
        "top_functions": _top_functions(analyzer.build_function_lookup(), top=top),
    }
```

- [ ] **Step 4: Run test, verify pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host_profiling.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acq4/mcp/host.py acq4/mcp/tests/test_host_profiling.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add profile_functions host helper with hot-spot ranking

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 9: host memory snapshot + pure heap-summary helper

**Files:**
- Modify: `acq4/mcp/host.py`
- Test: `acq4/mcp/tests/test_host_profiling.py`

**Interfaces:**
- Produces:
  - `host._summarize_heap(heap_stats, top: int = 15) -> dict` — pure; `{"total_bytes", "top_types": [{"type", "count", "bytes"}...]}`. Consumes a guppy-like object exposing `.size` and `.bytype` (indexable, each item has `.kind`, `.count`, `.size`).
  - `host.memory_snapshot(name=None, top: int = 15) -> dict` — takes a snapshot via the live memory profiler; if a previous snapshot exists, also returns a `growth` summary of `current - previous`.
- Consumes: `MemoryProfiler.take_snapshot`, `MemoryProfiler.snapshots`, `MemorySnapshot.heap_stats`/`.name`/`.is_valid` (Task 6). guppy heap subtraction: `current.heap_stats - previous.heap_stats`.

- [ ] **Step 1: Write failing test (pure helper)**

Append to `acq4/mcp/tests/test_host_profiling.py`:

```python
class _TypeStat:
    def __init__(self, kind, count, size):
        self.kind = kind
        self.count = count
        self.size = size


class _Heap:
    def __init__(self, size, rows):
        self.size = size
        self.bytype = rows  # list is indexable + has len, like a guppy partition


def test_summarize_heap_reports_total_and_top_types():
    heap = _Heap(300, [_TypeStat("dict", 2, 200), _TypeStat("list", 5, 100)])
    summary = host._summarize_heap(heap, top=1)
    assert summary["total_bytes"] == 300
    assert summary["top_types"] == [{"type": "dict", "count": 2, "bytes": 200}]
```

- [ ] **Step 2: Run test, verify fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host_profiling.py -k summarize_heap -v`
Expected: FAIL with `AttributeError: ... no attribute '_summarize_heap'`.

- [ ] **Step 3: Implement**

In `acq4/mcp/host.py` add:

```python
def _summarize_heap(heap_stats, top=15):
    """Summarize a guppy heap (or heap diff): total bytes and the top types by size.

    Pure aside from reading the guppy object's `.size`/`.bytype` interface, so it is
    testable with a fake exposing those.
    """
    by_type = heap_stats.bytype
    rows = []
    for i in range(min(top, len(by_type))):
        stat = by_type[i]
        rows.append({"type": str(stat.kind), "count": stat.count, "bytes": stat.size})
    return {"total_bytes": heap_stats.size, "top_types": rows}


def memory_snapshot(name=None, top=15):
    """Take a guppy heap snapshot into the live Profiler window and summarize it.

    Repeated calls accumulate snapshots in the window (the memory-over-time series). When
    a prior snapshot exists, `growth` summarizes the heap increase since the last one.
    Must run on the GUI thread path via run_in_gui_thread (touches the widget).
    """
    from acq4.util import task

    tabs = task.run_in_gui_thread(_profiler_tabs)
    mp = tabs.memory_profiler
    if not hasattr(mp, "take_snapshot"):
        raise RuntimeError(
            "Installed rtprofile lacks the headless take_snapshot API; update rtprofile."
        )
    previous = mp.snapshots[-1] if mp.snapshots else None
    snapshot = task.run_in_gui_thread(mp.take_snapshot, name)
    if not snapshot.is_valid:
        return {"name": snapshot.name, "error": snapshot.error_message}
    out = {"name": snapshot.name, "snapshot": _summarize_heap(snapshot.heap_stats, top=top)}
    if previous is not None and previous.is_valid:
        out["growth_since"] = previous.name
        out["growth"] = _summarize_heap(snapshot.heap_stats - previous.heap_stats, top=top)
    return out
```

- [ ] **Step 4: Run test, verify pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host_profiling.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acq4/mcp/host.py acq4/mcp/tests/test_host_profiling.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add memory_snapshot host helper with heap-diff summary

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 10: `sample_resources()` extraction + host `health_series` and `profile_qt_events`

**Files:**
- Modify: `acq4/util/resource_monitor.py`, `acq4/mcp/host.py`
- Test: `acq4/util/tests/test_resource_monitor.py` (create), `acq4/mcp/tests/test_host_profiling.py`

**Interfaces:**
- Produces:
  - `resource_monitor.sample_resources(app=None) -> dict` — `{"cpu_percent", "memory_percent", "qt_activity"}`; `qt_activity` is `app.activity_fraction * 100` when available else `None`. Pure aside from psutil/app reads.
  - `host.health_series(seconds=10.0, interval=1.0) -> dict` — `{"interval": ..., "samples": [{"t", "cpu_percent", "memory_percent", "qt_activity", "latency_ms"}...]}`.
  - `host.profile_qt_events(seconds=10.0, top=15) -> dict` — top rows of `QApplicationProfile.get_statistics()`.
- Consumes: `psutil`, `QApplication.instance().activity_fraction`, `task.run_in_gui_thread` (latency), `QtEventProfiler.start_session/stop_session` + `QApplicationProfile.get_statistics()` (Task 6).

- [ ] **Step 1: Write failing test for sample_resources**

Create `acq4/util/tests/test_resource_monitor.py`:

```python
"""Tests for the headless resource-sampling helper used by acq4-mcp health_series."""

import acq4.util.resource_monitor as rm


class _App:
    activity_fraction = 0.25


def test_sample_resources_reports_cpu_and_memory(monkeypatch):
    monkeypatch.setattr(rm.psutil, "cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(
        rm.psutil, "virtual_memory", lambda: type("M", (), {"percent": 40.0})()
    )
    sample = rm.sample_resources(app=_App())
    assert sample["cpu_percent"] == 12.5
    assert sample["memory_percent"] == 40.0
    assert sample["qt_activity"] == 25.0


def test_sample_resources_without_qt_activity(monkeypatch):
    monkeypatch.setattr(rm.psutil, "cpu_percent", lambda interval=None: 1.0)
    monkeypatch.setattr(
        rm.psutil, "virtual_memory", lambda: type("M", (), {"percent": 2.0})()
    )
    sample = rm.sample_resources(app=object())
    assert sample["qt_activity"] is None
```

- [ ] **Step 2: Run test, verify fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_resource_monitor.py -v`
Expected: FAIL with `AttributeError: module 'acq4.util.resource_monitor' has no attribute 'sample_resources'`.

- [ ] **Step 3: Implement sample_resources**

In `acq4/util/resource_monitor.py`, add a module-level function (above the widget class):

```python
def sample_resources(app=None):
    """Return a one-shot resource sample: CPU %, memory %, and Qt activity %.

    qt_activity is app.activity_fraction * 100 when a ProfiledQApplication is active,
    else None. Shared by ResourceMonitorWidget and the acq4-mcp health_series tool.
    """
    try:
        cpu = psutil.cpu_percent(interval=None)
    except Exception:
        cpu = None
    try:
        memory = psutil.virtual_memory().percent
    except Exception:
        memory = None
    qt_activity = None
    fraction = getattr(app, "activity_fraction", None) if app is not None else None
    if fraction is not None:
        qt_activity = fraction * 100
    return {"cpu_percent": cpu, "memory_percent": memory, "qt_activity": qt_activity}
```

- [ ] **Step 4: Run test, verify pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_resource_monitor.py -v`
Expected: PASS.

- [ ] **Step 5: Implement host health_series + profile_qt_events**

In `acq4/mcp/host.py` add:

```python
def health_series(seconds=10.0, interval=1.0):
    """Sample CPU/memory/Qt-activity/event-loop-latency every `interval` for `seconds`.

    Returns a time series. Must run off the GUI thread (it sleeps between samples);
    latency is a GUI-thread round-trip timing per sample.
    """
    import time

    from acq4.util import task
    from acq4.util.Qt import QApplication
    from acq4.util.resource_monitor import sample_resources

    app = QApplication.instance()
    samples = []
    start = time.perf_counter()
    n = max(1, int(seconds / interval))
    for _ in range(n):
        t0 = time.perf_counter()
        task.run_in_gui_thread(lambda: None)  # measure GUI-thread responsiveness
        latency_ms = (time.perf_counter() - t0) * 1000
        sample = sample_resources(app=app)
        sample["t"] = time.perf_counter() - start
        sample["latency_ms"] = latency_ms
        samples.append(sample)
        time.sleep(interval)
    return {"interval": interval, "samples": samples}


def profile_qt_events(seconds=10.0, top=15):
    """Profile the Qt event loop for `seconds`; return the busiest event types.

    Requires ACQ4 started with --qt-profile (ProfiledQApplication); otherwise returns an
    error dict. Drives the live Profiler window's Qt tab.
    """
    import time

    from acq4.util import task

    tabs = task.run_in_gui_thread(_profiler_tabs)
    qp = tabs.qt_profiler
    if not hasattr(qp, "start_session"):
        raise RuntimeError(
            "Installed rtprofile lacks the headless start_session API; update rtprofile."
        )
    try:
        task.run_in_gui_thread(qp.start_session, None, False)
    except RuntimeError as exc:
        return {"error": str(exc)}
    time.sleep(seconds)
    profile = task.run_in_gui_thread(qp.stop_session)
    stats = profile.get_statistics(group_by="type")
    return {"session": profile.name, "top_events": stats[:top]}
```

- [ ] **Step 6: Write + run a formatting test for health_series structure**

Append to `acq4/mcp/tests/test_host_profiling.py` a test that monkeypatches `time.sleep`, `run_in_gui_thread`, and `sample_resources` so `health_series` is exercised without Qt:

```python
def test_health_series_collects_expected_sample_count(monkeypatch):
    import time

    import acq4.mcp.host as h
    import acq4.util.resource_monitor as rm
    from acq4.util import Qt, task

    # health_series does local `import time`, `from acq4.util import task`, `from
    # acq4.util.Qt import QApplication`, and `from acq4.util.resource_monitor import
    # sample_resources` at call time, so patching each on its home module takes effect.
    monkeypatch.setattr(Qt.QApplication, "instance", staticmethod(lambda: object()))
    monkeypatch.setattr(task, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.setattr(
        rm, "sample_resources",
        lambda app=None: {"cpu_percent": 1.0, "memory_percent": 2.0, "qt_activity": None},
    )
    monkeypatch.setattr(time, "sleep", lambda s: None)

    out = h.health_series(seconds=3.0, interval=1.0)
    assert len(out["samples"]) == 3
    assert out["samples"][0]["latency_ms"] >= 0
```

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host_profiling.py -v`
Expected: PASS. (If importing `acq4.util.Qt` requires a display, mark this test `@pytest.mark.skipif` on no Qt; the pure helpers in Tasks 8–9 remain the primary coverage.)

- [ ] **Step 7: Commit**

```bash
git add acq4/util/resource_monitor.py acq4/util/tests/test_resource_monitor.py acq4/mcp/host.py acq4/mcp/tests/test_host_profiling.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add health_series and profile_qt_events host helpers

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 11: connection delegators for the four profiling calls

**Files:**
- Modify: `acq4/mcp/connection.py`
- Test: `acq4/mcp/tests/test_connection.py`

**Interfaces:**
- Produces on `ConnectionManager`: `profile_functions(seconds=10.0, top=15, port=None, host=None)`, `memory_snapshot(name=None, top=15, port=None, host=None)`, `profile_qt_events(seconds=10.0, top=15, port=None, host=None)`, `health_series(seconds=10.0, interval=1.0, port=None, host=None)` — each delegates to the host over teleprox with a generous `_timeout` (>= seconds + 15).

- [ ] **Step 1: Write failing test**

Add to `_FakeHostModule` in `test_connection.py`:

```python
    def profile_functions(self, seconds, top, **kw):
        self.recorder.append(("profile_functions", self.host, self.port, seconds, top, kw))
        return {"top_functions": []}
```

Add:

```python
def test_profile_functions_delegates_with_timeout(manager, recorder):
    manager.connect(5000)
    manager.profile_functions(seconds=5.0, top=3)
    call = recorder[-1]
    assert call[0] == "profile_functions"
    assert call[3] == 5.0 and call[4] == 3
    assert call[5]["_timeout"] >= 20.0  # seconds + margin
```

- [ ] **Step 2: Run test, verify fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_connection.py -k profile_functions -v`
Expected: FAIL with `AttributeError: 'ConnectionManager' object has no attribute 'profile_functions'`.

- [ ] **Step 3: Implement**

In `acq4/mcp/connection.py` add (following the `_run`/`_resolve` pattern):

```python
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
```

- [ ] **Step 4: Run test, verify pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_connection.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acq4/mcp/connection.py acq4/mcp/tests/test_connection.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add profiling delegators to connection manager

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

### Task 12: profiling MCP tools + docs

**Files:**
- Modify: `acq4/mcp/server.py`, `acq4/mcp/README.md`

**Interfaces:**
- Consumes: the four `ConnectionManager` profiling methods.
- Produces: MCP tools `profile_functions`, `memory_snapshot`, `profile_qt_events`, `health_series`.

- [ ] **Step 1: Implement the tools**

In `acq4/mcp/server.py`, inside `build_server()` after `get_log`, add four tools; each wraps the delegator, catches `NotConnectedError`, and returns `json.dumps(..., indent=2, default=str)`:

```python
    @server.tool()
    def profile_functions(
        seconds: float = 10.0, top: int = 15,
        port: Optional[int] = None, host: Optional[str] = None,
    ) -> str:
        """Profile all-thread function calls for `seconds`; return the hottest functions.

        Opens ACQ4's Profiler window if needed and collects there (visible to the human).
        Observability only — adds profiling overhead but moves no hardware. Note: installs
        setprofile across all threads; keep windows short on a busy rig.
        """
        try:
            return json.dumps(
                _connection.profile_functions(seconds=seconds, top=top, port=port, host=host),
                indent=2, default=str,
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"

    @server.tool()
    def memory_snapshot(
        name: Optional[str] = None, top: int = 15,
        port: Optional[int] = None, host: Optional[str] = None,
    ) -> str:
        """Take a guppy heap snapshot into the Profiler window and summarize it.

        Repeated calls build a memory-over-time series; each call also reports heap growth
        since the previous snapshot. Requires guppy3 on the rig.
        """
        try:
            return json.dumps(
                _connection.memory_snapshot(name=name, top=top, port=port, host=host),
                indent=2, default=str,
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"

    @server.tool()
    def profile_qt_events(
        seconds: float = 10.0, top: int = 15,
        port: Optional[int] = None, host: Optional[str] = None,
    ) -> str:
        """Profile the Qt event loop for `seconds`; return the busiest event types.

        Requires ACQ4 started with --qt-profile; otherwise returns an error note.
        """
        try:
            return json.dumps(
                _connection.profile_qt_events(seconds=seconds, top=top, port=port, host=host),
                indent=2, default=str,
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"

    @server.tool()
    def health_series(
        seconds: float = 10.0, interval: float = 1.0,
        port: Optional[int] = None, host: Optional[str] = None,
    ) -> str:
        """Sample CPU/memory/Qt-activity/event-loop-latency over `seconds` and return the series."""
        try:
            return json.dumps(
                _connection.health_series(seconds=seconds, interval=interval, port=port, host=host),
                indent=2, default=str,
            )
        except NotConnectedError as exc:
            return f"Not connected: {exc}"
```

- [ ] **Step 2: Verify build + tool registration**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "from acq4.mcp.server import build_server; import asyncio; print(sorted(t.name for t in asyncio.run(build_server().list_tools())))"`
Expected: list includes `profile_functions`, `memory_snapshot`, `profile_qt_events`, `health_series`.

- [ ] **Step 3: Update README**

Add the four tools to the Tools table with one-line descriptions, and a short "Profiling" section explaining they drive the live Profiler window, that function/Qt profiling adds overhead (keep windows short given the teleprox load caveat in KNOWN_ISSUES.md), and that Qt profiling needs `--qt-profile` and memory needs `guppy3`.

- [ ] **Step 4: Commit**

```bash
git add acq4/mcp/server.py acq4/mcp/README.md
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: expose profiling MCP tools and document them

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>"
```

---

## Final verification

- [ ] **Full MCP test suite green**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/ acq4/util/tests/test_resource_monitor.py -v`
Expected: PASS (all), output pristine.

- [ ] **rtprofile PR green + linked**

Confirm the rtprofile draft PR exists and its `tests/test_headless_api.py` passes.

- [ ] **black formatting**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m black acq4/mcp acq4/util/resource_monitor.py` and re-run the test suite.

- [ ] **Manual live smoke (documented in the acq4 PR)**

Against a rig started with `python -m acq4 --teleprox 40104 --qt-profile`: `connect_via_ssh`/`connect_acq4`, `execute_code` persistence across two calls, `reset_namespace`, `profile_functions(seconds=3)`, `memory_snapshot()` twice, `health_series(seconds=3)` — all return sane data and the Profiler window is populated.

- [ ] **Open the acq4 draft PR**

```bash
git push -u martin feat/acq4-mcp
gh pr create --draft --title "acq4-mcp: persistence, profiling, and SSH-tunnel tools" --body "Implements docs/superpowers/specs/2026-07-13-acq4-mcp-features-design.md. Depends on rtprofile headless-API PR. 🧙 Built with WOZCODE"
```
(The `feat/acq4-mcp` PR #22 may already exist; if so these commits extend it — no new PR needed.)
