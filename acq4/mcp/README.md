# acq4-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an AI client (Claude Desktop,
Claude Code, etc.) inspect and drive a **running** ACQ4 instance by executing Python
inside the ACQ4 process. It connects over ACQ4's existing teleprox `RPCServer`.

> **Status — not yet production-safe.** Concurrent or high-rate MCP traffic corrupts the
> teleprox transport, which can kill ACQ4's RPCServer thread or (intermittently) abort the
> whole process with a libzmq assertion. This is a teleprox-level bug exposed — not caused
> — by the MCP, and is **not** fixed by the MCP's client-side serialization. See
> [KNOWN_ISSUES.md](KNOWN_ISSUES.md). Safe for gentle, single-threaded, interactive use;
> do not point it at a production rig where a crash is costly until teleprox is hardened.

## How it works

```
AI client  --stdio-->  acq4-mcp server  --teleprox TCP-->  ACQ4 process
           (mcp SDK)   (this package)                      (acq4.mcp.host)
```

- `acq4/mcp/host.py` runs **inside** ACQ4 (where the Manager and Qt GUI live) and does the
  actual work. It has no dependency on the `mcp` SDK, so it ships and imports on every
  ACQ4 install.
- `acq4/mcp/connection.py` is the client-side teleprox connection manager.
- `acq4/mcp/server.py` is the thin FastMCP stdio server. It imports the `mcp` SDK, so only
  the machine running the server needs the extra installed.

## Setup

1. Install the MCP extra on the machine that will run the server:

   ```
   pip install acq4[mcp]
   ```

2. Start ACQ4 with a teleprox server:

   ```
   acq4 --teleprox 5000
   ```

   With a bare `--teleprox` (no port) ACQ4 picks a random port and prints
   `Teleprox server listening on tcp://127.0.0.1:<port>` at startup.

3. Register the MCP server with your client. Example `mcpServers` config:

   ```json
   {
     "mcpServers": {
       "acq4": {
         "command": "acq4-mcp"
       }
     }
   }
   ```

4. In the conversation, connect to the rig: call `connect_acq4(port=5000)`. The port is
   supplied at runtime (not baked into the config), so when ACQ4 restarts on a different
   port you just call `connect_acq4` again -- no need to restart the MCP server.

### Remote rigs

ACQ4 binds its teleprox server to `127.0.0.1`. To reach a rig on another machine, use
`connect_via_ssh`, which opens an SSH tunnel and connects to ACQ4 in one step:

```python
connect_via_ssh("minirig", 40104)  # relies on ~/.ssh/config
```

If `~/.ssh/config` has `Host minirig`, this will tunnel to the remote rig's ACQ4 (started
with `--teleprox 40104`) and connect you to it. A free local port is chosen automatically.
To close the tunnel, call `disconnect_ssh("minirig")`.

## Tools

| Tool | Description |
|------|-------------|
| `connect_acq4(port, host="127.0.0.1")` | Connect to a running ACQ4 and make it the active target. Returns an identity/sanity summary. |
| `connect_via_ssh(target, remote_port, local_port=None)` | Open an SSH tunnel to a remote rig and connect to its ACQ4 in one step. Returns the rig identity summary. |
| `disconnect_ssh(target=None)` | Close the SSH tunnel for `target` (or all tunnels if omitted). |
| `execute_code(code, gui_thread=False, timeout=30.0, port=None, host=None)` | Execute arbitrary Python in the ACQ4 process. |
| `reset_namespace(port=None, host=None)` | Clear the persistent execute_code namespace. |
| `list_devices(port=None, host=None)` | Device name -> class mapping (read-only). |
| `list_modules(port=None, host=None)` | Loaded and configured module names (read-only). |
| `manager_state(port=None, host=None)` | Storage dirs, device count, config keys (read-only). |
| `get_log(lines=50, port=None, host=None)` | Tail of the ACQ4 log file (read-only). |
| `profile_functions(seconds=10.0, top=15, port=None, host=None)` | Profile all-thread function calls; return the hottest functions in the Profiler window. |
| `memory_snapshot(name=None, top=15, port=None, host=None)` | Take a guppy heap snapshot and build a memory-over-time series in the Profiler window. |
| `profile_qt_events(seconds=10.0, top=15, port=None, host=None)` | Profile the Qt event loop; return the busiest event types (requires `--qt-profile`). |
| `health_series(seconds=10.0, interval=1.0, port=None, host=None)` | Sample CPU/memory/Qt-activity/event-loop-latency over time. |

`execute_code` runs in a persistent namespace shared across calls (variables persist
across calls). The namespace is seeded with `man` (the ACQ4 Manager) and `acq4` on the first
call (or after a `reset_namespace` call). It returns captured stdout/stderr, the value of a
trailing expression, and any traceback. Use `reset_namespace` to discard accumulated state
and start fresh.

## Profiling

The four profiling tools (`profile_functions`, `memory_snapshot`, `profile_qt_events`,
`health_series`) drive ACQ4's live Profiler window and collect observability data without
mutating running state.

- **`profile_functions` and `profile_qt_events`** add overhead (they install per-thread
  profiling callbacks). Keep profiling windows short on a busy rig to avoid exacerbating
  the teleprox load issues documented in [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
- **`profile_qt_events`** requires ACQ4 to be started with `--qt-profile`.
- **`memory_snapshot`** requires `guppy3` installed on the rig. Repeated calls build a
  memory-over-time series; each call reports heap growth since the previous snapshot.

## GUI thread: `gui_thread=False` vs `gui_thread=True`

This is the central hazard. Choosing wrong can **crash or freeze** ACQ4.

- **`gui_thread=False` (default)** -- code runs off the GUI thread. Use this for anything
  **blocking or long-running**: device/stage/pipette moves, `.wait()`, acquisitions,
  `sleep`, patch state changes. Running such code on the GUI thread would **freeze or
  deadlock** the entire ACQ4 application.
- **`gui_thread=True`** -- code is marshalled onto the Qt GUI thread and blocks until it
  returns. Use this **only** for fast, non-blocking access to Qt widgets/objects or GUI
  state. Touching Qt objects from another thread risks a **segfault** -- but never run
  blocking work on the GUI thread.

Rule of thumb: if it touches a Qt widget and returns immediately, `gui_thread=True`.
Everything else (especially anything that moves hardware or waits) stays `gui_thread=False`.

## Safety: do not mutate without approval

The read-only tools (`list_devices`, `list_modules`, `manager_state`, `get_log`) are safe to
call freely. `execute_code` can do anything Python can do in the ACQ4 process. There is no
enforcement layer -- no code can reliably tell whether arbitrary Python mutates state -- so
this is a discipline the agent must follow:

> Inspect freely. Obtain **explicit user approval** before executing anything that changes
> running state or moves hardware: stage/pipette moves, pressure changes, clamp mode
> changes, starting tasks or acquisitions, or writing config/data. When in doubt, treat it
> as mutating and ask first.
