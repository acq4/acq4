# acq4-mcp: persistence, profiling, and SSH-tunnel features

Design for three additions to the `acq4-mcp` server: a persistent exec namespace,
profiling tools that drive ACQ4's live Profiler window, and one-call SSH-tunnel
connection. All three slot into the existing three-layer structure
(`host.py` inside ACQ4, `connection.py` client-side teleprox manager, `server.py`
FastMCP glue) without new architecture.

## Status / scope

- Branch: `feat/acq4-mcp`.
- All three features ship in this one spec/plan.
- Feature 2 requires a companion change in the `rtprofile` package
  (`github.com/campagnola/rtprofile`), which is under the same owner. It will be
  cloned locally, installed editable, edited, and PR'd upstream.

## Background

The existing MCP (see `2026-07-03-acq4-mcp-design.md`) exposes `connect_acq4`,
`execute_code`, `list_devices`, `list_modules`, `manager_state`, `get_log`.
`execute_code` builds a **fresh namespace every call** via `host._build_namespace()`,
seeded with `man` and `acq4`. `connect_acq4` assumes any SSH tunnel to a remote rig
already exists. ACQ4's profiling lives in the `Profiler` module
(`acq4/modules/Profiler/module.py`), which embeds `rtprofile.profiler_tabs.ProfilerTabs`
— a `QWidget` holding three sub-profilers (`.function_profiler`, `.qt_profiler`,
`.memory_profiler`). Lightweight health metrics come from
`acq4/util/resource_monitor.py` (CPU/mem/Qt-activity/latency, sampled once/sec inside a
widget) and `ProfiledQApplication.activity_fraction` (only present when ACQ4 is started
with `--qt-profile`).

---

## Feature 1 — Persistent exec namespace

### Behavior

`execute_code` calls share **one long-lived namespace** on the ACQ4 side (REPL
semantics): variables defined in one call are visible in the next. A new
`reset_namespace` tool clears it back to a fresh seeded state.

### Host changes (`acq4/mcp/host.py`)

- Introduce a module-level `_PERSISTENT_NS` (initially `None`).
- `_get_namespace()` lazily builds it via the existing `_build_namespace()` on first
  use and returns the same dict thereafter.
- Heal `man`: if `_PERSISTENT_NS['man']` is `None` (Manager didn't exist when the
  namespace was first built), re-resolve `acq4.getManager()` and update it — **without**
  clobbering user-defined variables.
- `execute(code, gui_thread=False)` execs against `_get_namespace()` instead of a fresh
  dict.
- `reset_namespace()` sets `_PERSISTENT_NS = None` and returns a small confirmation dict
  (e.g. `{"reset": True}`), so the next `execute` rebuilds it.

Persistence is process-global on the ACQ4 side: it survives MCP-server restarts and is
shared across clients connected to the same rig. This is intended and documented.

### Client + server changes

- `ConnectionManager.reset_namespace(port=None, host=None)` delegating to the host
  (mirrors the existing `_run`/`_resolve` pattern).
- `server.py`: new `reset_namespace` MCP tool.
- Update `execute_code`'s docstring and `README.md`: state persists across calls; use
  `reset_namespace` to start clean.

### Testing

Unit tests in `acq4/mcp/tests/test_host.py` (pure, no Qt/mcp deps):
- a variable set in one `execute` is visible in the next;
- `reset_namespace` drops it;
- `man` re-heals from `None` once a Manager is available, without wiping user vars.

---

## Feature 2 — Profiling tools (drive the live Profiler window)

### Model

MCP tools locate the running `Profiler` module's `ProfilerTabs`
(auto-`man.loadModule('Profiler')` when absent), trigger collection through the **same
code paths the UI buttons use** so results land in the window the human sees, then read
the result containers back and return a compact aggregation as text.

### rtprofile refactor (companion PR)

The sub-profilers' collection logic is currently welded to widgets (reads `QLineEdit`
text, toggles buttons). Extract the non-UI core of each into public **headless**
methods, and have the existing button handlers call them (a true refactor — no button
behavior change). Each new method appends to the same results list *and* calls the
existing `_addResultToList`, so the window stays in sync:

- `FunctionProfiler.start_session(name=None, max_duration=None)` /
  `stop_session() -> ProfileResult`
- `MemoryProfiler.take_snapshot(name=None) -> MemorySnapshot`
- `QtEventProfiler.start_session(name=None, hold_receivers=False)` /
  `stop_session() -> QApplicationProfile`

rtprofile tests cover the new public methods and that the button handlers still work
through them.

### ACQ4-side host helpers (`acq4/mcp/host.py`)

Profiling helpers live in `host.py`, keeping the single `acq4.mcp.host` teleprox import
surface that `connection.py` already uses. (Split into a dedicated module only if the
file grows unwieldy.)

A `_profiler_tabs()` helper returns the live `ProfilerTabs`, loading the Profiler module
if needed. GUI-touching steps run via `task.run_in_gui_thread`; timed windows sleep off
the GUI thread.

Host functions, each returning a JSON-able dict:
- `profile_functions(seconds)` — `function_profiler.start_session()`, sleep `seconds` off
  the GUI thread, `stop_session()`, then use `rtprofile`'s `ProfileAnalyzer` to return
  the top-N hottest functions.
- `memory_snapshot()` — `memory_profiler.take_snapshot()`; if a previous snapshot exists,
  return a diff against it (repeated calls build the over-time series in the window).
- `profile_qt_events(seconds)` — `qt_profiler.start_session()`, sleep, `stop_session()`,
  return `QApplicationProfile.get_statistics()` top rows. Detect and clearly report when
  ACQ4 was not started with `--qt-profile` (no `activity_fraction`/profile support).
- `health_series(seconds, interval=1.0)` — sample CPU / memory / `activity_fraction` /
  event-loop latency at `interval` for `seconds` and return the time series. The
  sampling logic is extracted from `resource_monitor` into a plain, headless-callable
  function (`sample_resources()`), reused by both the widget and this tool.

Graceful degradation: if `rtprofile` lacks the new public methods (unpatched install),
the host raises a clear, actionable error rather than crashing ACQ4.

### Client + server changes

`ConnectionManager` gains `profile_functions`, `memory_snapshot`, `profile_qt_events`,
`health_series` (all through `_run`/`_resolve`). `server.py` exposes matching MCP tools
with docstrings noting these are read-only-ish observability tools (they add profiling
overhead but don't move hardware).

### Caveat (documented, not solved)

Function/Qt profiling installs `setprofile_all_threads`, which touches the teleprox
handler thread and adds per-call overhead. Given the known teleprox-under-load fragility
(`KNOWN_ISSUES.md`), tools keep windows short and rely on the existing single-threaded
MCP serialization.

### Testing

- Pure helpers (top-N aggregation, snapshot diffing, `health_series` formatting) unit
  tested with fabricated `ProfileResult` / `MemorySnapshot` / statistics objects.
- rtprofile-side tests for the new public methods.
- Live path (Qt app + Manager + guppy) verified **manually** against a running rig — no
  headless Qt/Manager integration harness this pass (agreed trade-off).

---

## Feature 3 — SSH-tunnel auto-connect

### Behavior

"connect to the acq4 running at minirig:40104" becomes a single tool call. A new
client-side `SSHTunnelManager` (its own module, `acq4/mcp/ssh_tunnel.py`) spawns and
tracks SSH tunnels; the tool then hands off to the existing `connect_acq4`.

### `SSHTunnelManager`

- `open(target, remote_port, local_port=None) -> local_port`: pick a free local port
  (bind `127.0.0.1:0`, read it back, close) when not given; spawn
  `ssh -N -L <local>:127.0.0.1:<remote> <target>` as a tracked `subprocess.Popen`
  (**not** `-f`, so we own the PID and can tear it down); poll the local port until it
  accepts a connection or a timeout elapses; on failure, capture ssh stderr and raise.
- Idempotent: an existing live tunnel for `(target, remote_port)` is reused (return its
  local port) instead of spawning a second.
- `close(target=None)`: terminate the tracked tunnel(s).
- `target` relies on `~/.ssh/config` for user/hostname/keys (so a bare alias like
  `minirig` works). The spawn is injectable (like `connection.py`'s
  `host_module_provider`) for tests.

### Server changes

- `connect_via_ssh(target, remote_port, local_port=None)`: `manager.open(...)` then
  `_connection.connect(local_port)`, returning the identity summary.
- `disconnect_ssh(target=None)`: `manager.close(...)`.
- README: document the alias workflow and that it supersedes the manual `ssh -L` step.

### Testing

Unit tests in a new `acq4/mcp/tests/test_ssh_tunnel.py` with the ssh spawn injected (no
real ssh): free-port selection, idempotent reuse, teardown, and failure surfacing.

---

## Files touched (summary)

- `acq4/mcp/host.py` — persistent namespace + `reset_namespace`; profiling host helpers.
- `acq4/mcp/connection.py` — delegators for the new host calls.
- `acq4/mcp/server.py` — new MCP tools (`reset_namespace`, four profiling tools,
  `connect_via_ssh`, `disconnect_ssh`).
- `acq4/mcp/ssh_tunnel.py` — new `SSHTunnelManager`.
- `acq4/mcp/README.md` — document persistence, profiling tools, SSH workflow.
- `acq4/mcp/tests/` — `test_host.py` additions, new `test_ssh_tunnel.py`.
- `acq4/util/resource_monitor.py` — extract headless `sample_resources()`.
- **rtprofile repo (companion PR):** public headless methods on the three sub-profilers.

## Non-goals

- Hardening teleprox against concurrent/sustained load (tracked separately).
- A headless Qt+Manager integration harness for Feature 2.
- Managing SSH known-hosts / key setup (delegated to the user's `~/.ssh/config`).
