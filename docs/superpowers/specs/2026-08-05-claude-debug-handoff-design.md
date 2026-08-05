# Debug This With Claude — Design

Date: 2026-08-05
Status: approved design, implemented
## Problem

When ACQ4 raises an unhandled exception or logs something suspicious, the operator's only
handoff to an AI assistant is copy-paste: select the traceback, open a terminal, paste, and
re-describe the rig from memory. Meanwhile `acq4.mcp` already exposes the running process —
devices, manager state, log, and optionally live exception frames — over teleprox. The
information needed for a good debugging session exists; nothing connects the moment of
failure to it.

This design adds a "Debug with Claude" action to the two places an operator notices a
problem: the error popup and the log window. The action assembles a context blob describing
the record, the rig, and how to connect back into the live process, then launches Claude
Code primed with it.

## Goals

- One click from a log record or error dialog to a primed Claude Code session.
- The primed session knows which rig it is looking at and how to inspect it live.
- Start teleprox on demand so live inspection does not depend on a flag chosen before the
  failure, and degrade to a useful text-only handoff when it is unavailable.
- Leave room for an in-ACQ4 panel later without rework.

## Non-goals

- No inline chat UI in this phase (see Phase 2).
- No new MCP tools; `acq4.mcp` is used as-is.
- No automatic remediation. Claude inspects and advises; the operator acts.

## Decisions

| Decision | Chosen | Rejected alternative |
|---|---|---|
| Delivery | Spawn external Claude Code now; inline panel later, sharing the context builder | Inline-only — slower to learn whether primed context is any good |
| Exception ring buffer | Stays opt-in via `--exception-buffer N`; action degrades to text-only when absent | Always-on retention — pins a stack of locals, which on a rig can mean image data |
| Record scope | Any log record, not just exceptions | Exceptions only — on a rig the interesting line is often a device warning |
| Tool restrictions | Prompt-level guidance only; no `--disallowed-tools` | Hard read-only floor — rejected as too restrictive for inspection |
| Buffer correlation | Prose instruction telling Claude to call `list_exceptions` itself | Heuristic type/message/line matching in Python |
| Config surface | Mirror `codeEditor.py`: `misc:` config key plus per-platform defaults | Bespoke settings mechanism |
| Prompt delivery | Temp markdown file, short pointer prompt on argv | Whole blob on argv — quoting and length fragility |
| Teleprox | Started on demand if absent, behind a one-time per-session confirmation | Requiring `--teleprox` up front — the flag you needed before the crash you didn't expect |

### On tool restrictions

A spawned Claude with the acq4 MCP can call `execute_code` against the live rig —
manipulators, pressure, protocols. `exec_in_exception_frame` is not safe by construction
either: dead frames still hold references to live device objects, so code in that namespace
can call methods on them.

A hard read-only floor via `--disallowed-tools` was considered and **rejected** in favour of
prompt-level guidance. The consequence is explicit: Claude Code's own permission prompt is
the only gate on a hardware-touching call. The prompt templates therefore steer toward
inspection tools first and ask before mutating, but this is advisory. If a rig ever wants
the hard floor, it is a one-line addition to the command template.

### Why teleprox starts on demand but the exception buffer does not

These look like inconsistent answers to the same question. They are not, because the two
costs differ in kind:

- A teleprox server costs **nothing until it is started**, and starting it late is equivalent
  to starting it early. So it can wait for the moment of need.
- The exception ring buffer costs **retained memory continuously** — every held exception pins
  a stack of locals, which on a rig can be image data — and cannot be started late at all.
  An exception that has already been handled is gone; arming the buffer after the fact
  captures nothing.

So teleprox is deferred to first use, while the buffer stays an explicit up-front choice the
operator makes when they expect to need frame-level detail.

## Architecture

```
ErrorDialog button ---\
                       >-- build_debug_context(record) --> markdown blob
LogViewer menu item --/                |
                                       v
                            invokeClaude(blob)
                                       |
                        temp .md  +  claudeCommand() format string
                                       |
                                       v
                          terminal emulator running `claude`
                                       |
                          (MCP, already global) --> connect_acq4(port)
                                       |
                                       v
                              the running ACQ4 process
```

The boundary that matters: `build_debug_context` is pure and Qt-free, so Phase 2's panel
reuses it unchanged.

### New module: `acq4/util/claude_debug.py`

Modelled directly on `acq4/util/codeEditor.py`, which already solves "launch an external
tool from a log interaction" including per-platform command discovery and a config override.

```python
suggestedTerminalOrder = ['wezterm', 'kitty', 'gnome-terminal', 'konsole', 'xterm']

def build_debug_context(record, log_tail=None) -> str:
    """Render a markdown debugging brief for a log record. Pure; no Qt, no subprocess."""

def claudeCommand() -> str:
    """Return a format string containing {contextFile}.

    Resolution order:
      1. acq4 config  misc: claudeCommand
      2. per-platform default from terminalCommands, first entry found on the system
    Raises if neither yields a command.
    """

def invokeClaude(context: str) -> None:
    """Write context to a temp .md and spawn claudeCommand()."""
```

`invokeClaude` writes with `tempfile.NamedTemporaryFile(suffix='.md', delete=False)` and
does **not** delete the file. The spawned process outlives the call, and the blob is useful
to re-read or re-launch. Temp-dir hygiene is the OS's job.

Config override, documented in the docstring the way `codeEditorCommand` documents its own:

```
<default.cfg>:
    misc:
        claudeCommand: 'wezterm start -- claude "Read {contextFile} and help me debug it"'
```

### Per-platform defaults

| Platform | Command template |
|---|---|
| linux | `<terminal> <exec-flag> claude "Read {contextFile} and help me debug it"`, terminal discovered from `suggestedTerminalOrder` |
| darwin | `open -a Terminal --args claude "Read {contextFile} ..."` |
| win32 | `wt.exe new-tab --title "ACQ4 debug" claude "Read {contextFile} ..."`, falling back to `start "ACQ4 debug" cmd /k claude "Read {contextFile} ..."` |

Each Linux terminal needs its own exec flag (`-e`, `--`, `-e` …), so `terminalCommands`
is a dict of full templates per terminal per platform, exactly like `editorCommands`.

All launches go through `subprocess.Popen(..., shell=True)`, matching `invokeCodeEditor`.
On Windows this also means `claude.cmd` resolves without special handling.

**The Windows and macOS templates are unverified** — see Open Questions.

### Teleprox lifecycle

Live inspection requires a teleprox server in the ACQ4 process. Today that only exists if
the operator passed `--teleprox` before starting — i.e. before the crash they did not expect.
So the action both *discovers* an existing server and can *start* one.

`acq4/__main__.py` creates `teleprox_debug_server` as a module-level local and only prints
its address; nothing stores it retrievably. Add to `acq4/mcp/__init__.py`:

```python
_teleprox_server = None      # server we started ourselves
_teleprox_address = None     # address of whichever server is serving

def set_teleprox_address(addr):
    """Record the address of a server started elsewhere (called by __main__)."""

def get_teleprox_address():
    """Return the current address, or None if no server is running."""

def ensure_teleprox_server():
    """Return an address, starting a server if none is running. Idempotent."""
```

`__main__.py` calls `set_teleprox_address(teleprox_debug_server.address)` right after the
existing `print`. No import of `__main__` from library code.

`ensure_teleprox_server()` constructs `RPCServer('tcp://127.0.0.1:*')` when needed.
`RPCServer.__init__` defaults to `run_thread=True` and starts its own daemon thread, which
is why `__main__.py` never calls `run_forever()` — so a runtime-constructed server behaves
identically to a startup one, and `.address` is readable immediately. Note the address is
`bytes`; decode it before formatting into the prompt.

#### The contract, made explicit

teleprox's own docstring states plainly that **RPCServer is not a secure server** and is
intended only for trusted use. Starting one opens a loopback port that permits arbitrary
code execution inside the ACQ4 process for the remainder of the session. Doing that silently
because someone clicked "Debug with Claude" on an INFO message would be an implicit contract
change, so:

1. **One-time per-session confirmation.** The first time `ensure_teleprox_server()` would
   start a server, a modal states what is being opened, that it lasts for the session, and
   that declining still produces a text-only handoff. Declining is remembered for the
   session and does not re-prompt; there is no persisted "don't ask again".
2. **Logged at WARNING**, including the address — so the fact appears in the log window the
   operator is already looking at, and in the session's log file.
3. **Documented** in the `acq4.mcp` module docstring, in `claude_debug.py`, and in the
   `--teleprox` argparse help, which should note that the server may also be started on
   demand.

An operator who passed `--teleprox` has already made this choice; no prompt appears.

#### Threading caveat (pre-existing)

`__main__.py` uses the plain `RPCServer`, not `QtRPCServer`, so MCP calls execute on the
teleprox thread rather than the Qt thread. Touching Qt objects from there is unsafe. This is
already true of the current MCP setup and is unchanged by on-demand start, but it bounds what
live inspection can safely reach and belongs in the prompt guidance.

### Entry points

**`ErrorDialog`** (`acq4/util/LogWindow.py`) — add a button beside `logBtn`:

```python
self.claudeBtn = Qt.QPushButton("Debug with Claude")
self.btnLayout.addWidget(self.claudeBtn)
self.claudeBtn.clicked.connect(self.claudeClicked)
```

`show()` already receives the `LogRecord`; it must retain the current one on `self` so
`claudeClicked` has something to hand to the builder. `nextMessage()` currently pops
pre-rendered HTML strings from `self.messages`; that list becomes a list of records so the
button stays correct as the operator steps through queued errors. Rendering to HTML moves
into the display path.

**`DocumentedLogViewer`** — teleprox's `LogViewer` already wires
`tree.customContextMenuRequested` to `_show_row_context_menu`. Override it, call super,
append a "Debug with Claude" action for the record under the cursor. This mirrors how the
class already extends `_on_item_clicked` for documentation links.

The log tail comes from the viewer's model — up to 50 records preceding the selected one.
The `ErrorDialog` path has no model, so it passes `log_tail=None` and the section is
omitted.

## The context blob

Markdown, assembled in this order. Sections whose data is unavailable are omitted, never
emitted empty.

1. **Rig identity** — hostname, ACQ4 version and git revision (via `acq4.util.gitversion`),
   manager base directory.
2. **How to connect** — the literal `connect_acq4(port=N)` call to make first, using the
   address from `ensure_teleprox_server()`. When the operator declined the confirmation, this
   becomes one sentence stating live inspection is unavailable by choice, so Claude works
   from the text alone rather than retrying a connection that cannot succeed. Also carries
   the note that MCP calls run on the teleprox thread, so Qt objects must not be touched.
3. **The record** — level name, logger name, timestamp, message, and the gentletask
   throughline chain when `record.throughline` is set.
4. **Traceback** — `traceback.format_exception(*record.exc_info)` when present.
5. **Live frame inspection** — when connecting is possible and a traceback exists: an
   instruction to call `list_exceptions`, match the entry against the traceback above, and
   use `get_exception_frame` / `exec_in_exception_frame` on it. Includes the note that the
   ring buffer is opt-in, so an empty list means ACQ4 was started without
   `--exception-buffer N` and text-only analysis is expected.
6. **Recent log** — the tail, when supplied.
7. **Task** — one of the three templates below.

### Why no buffer correlation in Python

Matching a `LogRecord` to a ring-buffer entry would be heuristic: `ErrorDialog` is fed by
the logging handler while the buffer is fed by `pyqtgraph.exceptionHandling` callbacks, and
the two paths share no identifier. Comparing exception type, message, and innermost
file/line would be fuzzy code needing its own tests, and would be dead weight whenever the
buffer is off — the common case.

Instead the blob asks Claude to call `list_exceptions` and do the matching. It is a task
Claude is good at, it self-describes when the buffer is empty, and it is prose rather than a
function.

### Prompt templates

Selected by `record.exc_info` and `record.levelno`:

| Condition | Task text |
|---|---|
| `exc_info` present, or `levelno >= ERROR` | Why did this break? Establish the failure mechanism from the traceback, then confirm it against live state if inspection is available. |
| `levelno == WARNING` | This looks suspicious. What is going on here — is it benign, or the first sign of a real problem? |
| otherwise (INFO and below) | Explain what this message means in the context of this rig, and offer possible next steps. |

Every template appends the same guidance paragraph: prefer inspection tools (`get_log`,
`list_devices`, `manager_state`, `health_series`, `get_exception_frame`) to build
understanding; this is a live scientific instrument, so ask before running anything that
could change device state.

## Phase 2: inline panel (deferred)

A dock widget backed by `claude-agent-sdk`, consuming `build_debug_context()` unchanged.
Requires:

- A new dependency — `claude-agent-sdk` is not currently in the `acq4-gl` environment.
  Belongs in a new optional extra, not the base install.
- An async-to-Qt bridge; the SDK is asyncio-native and ACQ4 is a Qt event loop.
- A rendered transcript widget.

One wrinkle to design for when Phase 2 starts: an inline agent whose tool calls re-enter the
same process via teleprox can deadlock the GUI if a blocking `execute_code` is dispatched
from the Qt thread. The SDK subprocess is separate, which helps, but the reentrancy needs
deliberate handling rather than assumption.

Nothing in Phase 1 blocks this, which is the point of keeping the builder pure.

## Testing

**Unit — `build_debug_context`.** Pure function, so this tier carries the weight. Matrix:
three template branches × `exc_info` present/absent × teleprox address present/absent ×
log tail supplied/omitted. Assertions: correct task text selected, `connect_acq4(port=N)`
present only with an address, unavailability sentence present only without one, traceback
section present only with `exc_info`, no empty section headers, throughline rendered when
set.

**Unit — `claudeCommand`.** Config value returned verbatim when set; falls back to platform
default when unset; raises a clear error when no terminal is discoverable. Patch
`sys.platform` and the discovery helper.

**Integration — `invokeClaude`.** Point `claudeCommand` at a stub script that records its
argv and exits. Assert the temp file exists, contains the expected sections, and that
`{contextFile}` was substituted with its path.

**Qt — entry points.** With `invokeClaude` patched: the `ErrorDialog` button exists and
passes the currently displayed record; stepping through queued errors with `nextBtn` updates
which record the button sends; the log viewer's context menu contains the action and it
passes the record under the cursor.

**Unit — `ensure_teleprox_server`.** Returns the existing address without starting anything
when one is already recorded, and without prompting. Starts exactly one server across
repeated calls. Returns `None` and does not start a server when the confirmation is declined,
and does not re-prompt on subsequent calls in the same session. Emits a WARNING containing
the address when it does start one. The confirmation and `RPCServer` are both patched; no
real port is bound in tests.

### On end-to-end coverage

A literal end-to-end test would spawn a real terminal, run a real `claude`, and drive a TUI
that talks to Anthropic's API. That is not automatable in CI and would not be a useful
signal if it were.

The stub-script integration test above is treated as the end-to-end tier: it exercises the
complete contract ACQ4 owns — context assembly, temp file creation, command formatting,
process spawn — and stops precisely where the external process begins. This is a stated
boundary, not a skipped tier. Manual verification of the actual launch is an open item below.

## Open questions

1. **Windows launch is unverified.** The `wt.exe` and `cmd /k` templates are best guesses;
   Claude Code has not been run from a Windows command line on these rigs. Needs manual
   verification on a Windows rig before the Windows default can be trusted. The config
   override means a wrong guess is a one-line fix, not a blocker.
2. **macOS launch is unverified**, same reasoning, lower priority.
3. **WSL breaks live inspection.** If Claude Code runs under WSL on a Windows rig,
   `connect_acq4` cannot reach ACQ4: teleprox binds to `tcp://127.0.0.1:*`, and from inside
   WSL2 that loopback is the WSL VM's own. On-demand start does not help — the new server
   binds the same interface. Text handoff still works. Native Windows `claude` avoids this;
   if WSL turns out to be necessary, teleprox binding needs revisiting as separate work.
4. **Is the confirmation modal wanted?** It is included because opening an exec-capable port
   is a different class of act from letting Claude inspect, and because it makes the contract
   visible at the moment it changes. If it proves to be friction on a trusted rig, dropping
   it is a one-line change — but that should be a deliberate call, not a default.
5. **Log tail length** is set at 50 records as a starting value, to be tuned once real
   sessions show whether it is too thin or mostly noise.


