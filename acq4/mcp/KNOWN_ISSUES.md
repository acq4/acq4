# acq4-mcp — known issues

## teleprox transport framing corrupts under concurrent / sustained load (blocker for production)

**Status:** open. Tracked upstream at
[campagnola/teleprox#40](https://github.com/campagnola/teleprox/issues/40). The MCP is safe
for gentle, single-threaded, interactive use, but is **not yet production-safe** on rigs
where a crash is costly.

### Symptom

While the MCP drives a running ACQ4, one of two things happens:

- **Recoverable:** ACQ4 logs `ValueError: Invalid RPC message: expected 6 parts, got N`
  from `teleprox/server.py` `run_forever` → `_read_one`. This exception is **unhandled**
  and terminates the RPCServer's `run_forever` thread, so the teleprox server (and
  MockClamp's `local_server="threaded"` callback server) goes deaf. The ACQ4 process keeps
  running but no longer answers teleprox.
- **Fatal:** a libzmq assertion `Assertion failed: false (src/object.cpp:142)` aborts the
  whole ACQ4 process with `SIGABRT`. This was the original crash, seen on the very first
  MCP call.

Both are the same underlying defect showing different faces.

### Root cause

Concurrent access to a single teleprox/zmq socket. libzmq sockets are not thread-safe;
when a socket's multipart send/receive is not atomic with respect to other access, frames
from different messages interleave. Captured evidence (from a single client thread's
socket):

```
expected 6 parts, got 2: [<caller>, {'module': 'acq4.mcp.host'}]   # a message tail
expected 6 parts, got 3: [<caller>, 'ping', 'auto']                # a message head
expected 6 parts, got 1: [b'import']                               # a lone action frame
```

A `ping` frame and a `call`/`import` frame from the same caller interleave — the multipart
sequences of two teleprox messages are split apart.

### Why the MCP exposes it (it does not cause it)

ACQ4 already runs several teleprox/zmq endpoints on the process-global
`zmq.Context.instance()`: the `--teleprox` RPCServer, the logging `LogServer`, and (per
device config) an RPCClient + threaded callback server for subprocess-backed devices such
as **MockClamp** (`MockClamp.py` calls `teleprox.start_process(local_server="threaded")`).
Before the MCP, nothing ever connected to the `--teleprox` RPCServer, so its thread sat
idle with no contention. The MCP wakes that thread and drives requests; under concurrency
or sustained throughput the transport corrupts.

### What was ruled out

- **Not `host.execute` / stdout redirection.** 400+ controlled `execute` round-trips under
  concurrent stdout/stderr/logging stress (with `log_stdio=True`, i.e. zmq-backed stdout)
  never crashed. `exec("1+1")` on the handler thread has no path to the failing sockets.
- **Not the imaging / Visualize3D path.** The camera/record threads use no teleprox/zmq;
  the record-thread appearing in the original crash stack was incidental.
- **Not fixed by serializing the MCP client.** Routing every MCP teleprox call through a
  single dedicated worker thread (one client socket, serialized) still corrupts under
  sustained concurrent load (4 caller threads → 1 executor, plain `execute("1+1")`, no
  nested calls). The contention is inside the teleprox transport, below the MCP layer.

### Reproduction

1. Launch: `python -m acq4 -x --teleprox 38750 -c config/mock/default.cfg -m Camera -m Visualize3D -m AutomationDebug`
2. From several threads, hammer `ConnectionManager.execute("1 + 1")` (or a single thread
   doing device access that proxies to the MockClamp child, e.g.
   `man.getDevice('Clamp1').getState()`).
3. Within seconds, ACQ4 logs `Invalid RPC message` and its RPCServer thread(s) die; the
   `object.cpp:142` abort appears intermittently.

### Candidate fixes (in teleprox — a separate repo; not yet done)

- Make teleprox's multipart socket send/receive atomic (per-socket lock), and/or strictly
  confine each socket to one thread including ping/reconnect probes.
- Make `run_forever` resilient: a malformed/partial message should be logged and skipped,
  not allowed to kill the server thread. This alone would prevent the "server goes deaf"
  cascade (but not the fatal libzmq assertion).

Until teleprox is hardened, avoid driving a production ACQ4's `--teleprox` server with
concurrent or high-rate MCP traffic.
