# acq4-mcp — MCP for executing code on a running ACQ4

**Status:** Design approved (pending written-spec review)
**Date:** 2026-07-03

## Purpose

Provide a Model Context Protocol (MCP) server that lets an AI client (Claude Desktop / Claude
Code / etc.) inspect and drive a running ACQ4 instance by executing arbitrary Python inside the
ACQ4 process. ACQ4 already exposes a teleprox `RPCServer` via its `--teleprox [port]` startup
option; this MCP is a teleprox client that reaches that server, imports `acq4`, gets the
`Manager`, and from there has full access to live rig state.

The MCP ships with ACQ4 so it can be deployed on any production rig.

## Background (verified against the codebase)

- **Teleprox server** is started in `acq4/__main__.py`: when `--teleprox` is passed, an
  `RPCServer` binds `tcp://127.0.0.1:*` (random port) or `tcp://127.0.0.1:<port>` and runs in a
  background thread. It prints `Teleprox server listening on <address>`.
- **Teleprox client API** (`teleprox/teleprox/client.py`, `proxy.py`): `RPCClient.get_client(address)`
  returns a per-thread client; `client._import('acq4')` returns an `ObjectProxy`. Teleprox actions
  are proxy operations only — `import`, `call_obj`, `get_obj`, `get_item`, `set_item`, `ping`,
  `close`. **There is no built-in "exec a code string" action**, so arbitrary code text must be
  run by a host-side helper that we ship.
- **GUI-thread marshalling** lives in `acq4/util/task.py`: `run_in_gui_thread(fn, *args, **kwargs)`
  runs `fn` on the Qt GUI thread and blocks for the result, or calls inline if already on the GUI
  thread.
- **Packaging**: `pyproject.toml` uses setuptools with `[project.optional-dependencies]` groups
  (`nidaq`, `micromanager`, ...) and `[tool.setuptools] packages = find(include=["acq4*"])`. There
  is no `[project.scripts]` section yet.

## Architecture

Two pieces, both inside the `acq4` package:

```
AI client (Claude)  --stdio-->  acq4-mcp server  --teleprox TCP-->  ACQ4 process
                                (acq4/mcp/server.py)                 (RPCServer thread)
                                                     imports & calls acq4/mcp/host.py
```

### Client side — `acq4/mcp/server.py`

- A FastMCP **stdio** server built on the `mcp` Python SDK.
- Holds a cache of teleprox `RPCClient`s keyed by `(host, port)` and tracks the **active**
  connection.
- Exposes the MCP tools (below). Each tool that needs ACQ4 resolves the target connection, does
  `host = client._import('acq4.mcp.host')`, and calls a single host-side function — so one MCP
  tool call is **one teleprox round-trip**, not dozens of proxied attribute accesses.
- Entry point: `main()` (console script `acq4-mcp`).

### ACQ4 side — `acq4/mcp/host.py`

- A plain module present in **every** ACQ4 install. **No dependency on the `mcp` package** — pure
  stdlib + acq4 — so it imports even on rigs where the `mcp` extra is not installed.
- Contains the functions the server calls over teleprox:
  - `execute(code, gui_thread=False)` — the workhorse (see below).
  - `manager_state()`, `list_devices()`, `list_modules()`, `get_log(lines)` — read-only
    inspection.
- All real work (exec, stdout capture, GUI-thread dispatch) happens here, where the GUI and
  Manager live.

## Connection handling

The teleprox port can change between ACQ4 restarts, and we do not want to restart the MCP each
time. Therefore the port is supplied **during the conversation**, not fixed at MCP launch.

- **`connect_acq4(port, host="127.0.0.1")`** — create/cache an `RPCClient` for that address, make
  it the active connection, and return a sanity payload (ACQ4 version, hostname, config/base dir,
  device count) so the caller can confirm the right rig.
- Every other tool accepts an **optional** `port` (and `host`) override; absent that, it uses the
  active connection. If there is no active connection and no `port`, the tool returns a clear
  "call connect_acq4 first" error.
- Re-point anytime by calling `connect_acq4` with a new port — **no MCP restart**. Cached clients
  make re-connecting to a prior port instant.
- Default `host` is `127.0.0.1`, matching ACQ4's bind. A remote rig requires an SSH tunnel; this
  is documented, not automated.

### Threading note (implementation constraint)

Teleprox `RPCClient`s are per-thread. The MCP server must ensure a given client is used from a
consistent thread (e.g. run tool bodies on a single worker thread, or key the client cache by
thread as teleprox's `get_client` already does). This is called out so the implementation plan
addresses it rather than discovering it at runtime.

## Tool surface

| Tool | Kind | Description |
|------|------|-------------|
| `connect_acq4(port, host="127.0.0.1")` | connection | Connect/re-point active ACQ4; returns sanity payload. |
| `execute_code(code, gui_thread=False, timeout=30.0, port=None, host=None)` | exec | Run `code` host-side; return captured output + result. |
| `list_devices(port=None, host=None)` | read-only | Device names and types. |
| `list_modules(port=None, host=None)` | read-only | Loaded/available modules. |
| `manager_state(port=None, host=None)` | read-only | Base/current dir, config summary (no module list). |
| `get_log(lines=50, port=None, host=None)` | read-only | Tail of the ACQ4 log. |

### `execute_code` semantics

- Runs `code` host-side in a **fresh namespace per call** (stateless — no leakage between calls),
  seeded with `man` (= `getManager()`) and `acq4`.
- Captures `stdout` and `stderr` produced during execution.
- Captures the value of the final expression, if the last statement is an expression, via `repr`
  (REPL-like convenience).
- On exception, returns the formatted traceback rather than raising across the MCP boundary.
- Returns a text payload combining: captured stdout/stderr, the result repr, and any traceback.
- `timeout` bounds the teleprox request; default 30.0s (teleprox's own default of 10s is too short
  for some inspection).

## GUI-thread policy (documented loudly)

`execute_code` takes `gui_thread` (default `False`). Host-side, `execute` dispatches on it using
`acq4.util.task.run_in_gui_thread`:

- **`gui_thread=True`** → run via `run_in_gui_thread` (blocks the GUI thread until done). Use
  **only** for: touching Qt widgets/objects, reading GUI state, or manager mutations that must
  occur on the GUI thread. **Must be fast and non-blocking.**
- **`gui_thread=False`** (default) → run directly on the teleprox handler thread. Use for anything
  blocking or long: device moves, `.wait()`, acquisitions, `sleep`, patch state changes.

**Failure modes, stated explicitly in the docs and the tool description:**

- Touching Qt objects from a non-GUI thread risks a **segfault**.
- Running blocking work on the GUI thread **freezes / deadlocks** the whole ACQ4 application.

This is the central hazard the tool must teach its caller about.

## Safety guidance (documentation only — not enforced)

No code can reliably classify whether arbitrary Python mutates state, so there is **no enforcement
layer**. Instead, guidance is placed where the agent reads it — the `execute_code` tool
description and the README:

> Inspect freely. Obtain **explicit user approval** before executing anything that mutates running
> state or moves hardware — stage/pipette moves, pressure changes, clamp mode changes, starting
> tasks/acquisitions, or writing config. When in doubt, treat it as mutating and ask first.

The read-only helper tools (`list_devices`, `list_modules`, `manager_state`, `get_log`) are safe
by construction and need no approval.

## Packaging & distribution

- New subpackage `acq4/mcp/`: `__init__.py`, `host.py`, `server.py`, `README.md`.
- `pyproject.toml`:
  - `[project.optional-dependencies]`: add `mcp = ["mcp"]`.
  - `[project.scripts]`: add `acq4-mcp = "acq4.mcp.server:main"` (new section).
- `host.py` has no `mcp` dependency, so it ships and imports on every ACQ4 install. Only the
  machine running the MCP **server** needs `pip install acq4[mcp]`.
- README includes a sample MCP client config snippet (`command: acq4-mcp`) and the SSH-tunnel note
  for remote rigs.

## Testing (TDD)

- **Unit** (no teleprox, no GUI): import `acq4.mcp.host` directly and test `execute()` — stdout
  capture, last-expression repr, exception/traceback formatting, namespace seeding (`man`/`acq4`),
  and `gui_thread` dispatch (with `run_in_gui_thread` mocked). Test the read-only helpers against a
  minimal/mocked Manager.
- **Integration**: test the server's connection cache and active-connection logic against a real
  in-process teleprox `RPCServer`.
- **End-to-end / collaborative**: against a real ACQ4 launched with `--teleprox <port>`, connect
  and exercise the tools interactively during development.

## Out of scope (YAGNI)

- Persistent cross-call exec namespace (explicitly chosen stateless).
- Read-only / write-mode enforcement toggles or per-call confirm tokens.
- Auto-discovery of the teleprox port.
- Long-running networked (HTTP/SSE) MCP transport.
- Rich structured per-operation tools (move_stage, get_frame, ...); `execute_code` is the escape
  hatch.
