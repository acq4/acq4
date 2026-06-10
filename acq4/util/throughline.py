"""Propagation of gentletask's throughline (the task-name chain identifying the
operation a log line belongs to) across the teleprox process boundary.

Built on teleprox's gentletask-agnostic call-opts-provider / context-hook seam
(``set_call_opts_provider`` / ``set_call_context_hook``): a client serializes its
current throughline frames into each outgoing call's opts, and a server
re-establishes them on its own throughline for the call's duration, so
``task_chain()`` and the log throughline show the full ancestry of the operation.

Propagation is OPT-IN. Nothing happens at import; a process must call
``enable_throughline_propagation()`` explicitly, once, to wire it up. Because the
client opts-provider and server context-hook are PROCESS-GLOBAL single slots,
enabling propagation claims those slots and is mutually exclusive with any other
user of that teleprox seam. For end-to-end propagation it must run in BOTH the
client process AND any server/child process that should re-establish the context.
"""
import contextlib

import gentletask
from gentletask import ThroughlineNameFilter

from teleprox import client as _client
from teleprox import server as _server
from teleprox.log import remote as _log_remote

# Opts key under which the serialized throughline frames travel. Frames are a
# tuple of plain ``{'name': ...}`` dicts (see SemanticStack.frames()), which the
# default serializers handle directly.
OPTS_KEY = "_throughline_frames"


def _opts_provider():
    """Provider for set_call_opts_provider: emit the caller's throughline frames.

    Returns an empty dict when there are no frames so the merge in
    ``RPCClient.call_obj`` adds nothing.
    """
    frames = gentletask.throughline.frames()
    if not frames:
        return {}
    return {OPTS_KEY: frames}


@contextlib.contextmanager
def _context_hook(opts):
    """Hook for set_call_context_hook: re-establish transferred frames, if any.

    Replays the transferred frames onto the server's throughline for the
    duration of the wrapped call via ``throughline.restore()``, then resets.
    Calls that carried no frames run under an unchanged throughline.

    ``restore()`` bypasses the ``required``-key validation that ``throughline``
    enforces on entry, so propagation does not depend on the client and server
    agreeing on identical ``required`` sets.

    NOTE: restore() REPLACES the stack for the block rather than appending to
    it -- any throughline frames the server already had on this thread are
    HIDDEN for the call duration and restored on exit.
    """
    frames = opts.get(OPTS_KEY) if opts else None
    if not frames:
        yield
        return
    with gentletask.throughline.restore(frames):
        yield


def _tag_log_sender():
    """Attach a ThroughlineNameFilter to this process's teleprox LogSender.

    LogSender.handle() applies its filters in the emitting thread, before
    queuing the record for the background send loop (which has no throughline
    context). Tagging there lets a child process's task context travel with its
    log records to the LogServer. A no-op in a process with no LogSender (e.g.
    the parent, which receives via a LogServer and tags its own records through
    the handler filters installed by logging_config).
    """
    sender = _log_remote.sender
    if sender is None:
        return
    if any(isinstance(f, ThroughlineNameFilter) for f in sender.filters):
        return
    sender.addFilter(ThroughlineNameFilter())


def enable_throughline_propagation():
    """Wire throughline propagation into this process's client and server.

    Registers the opts provider (client side) and context hook (server side),
    and tags outgoing log records with the throughline (child side). Safe to
    call repeatedly. Call it ONCE per process. For end-to-end propagation it
    must run in BOTH the client process and any server/child process that should
    re-establish the transferred context.

    This claims the process-global single provider/hook slots and is therefore
    mutually exclusive with any other user of teleprox's
    ``set_call_opts_provider`` / ``set_call_context_hook`` seam.
    """
    _client.set_call_opts_provider(_opts_provider)
    _server.set_call_context_hook(_context_hook)
    _tag_log_sender()


def disable_throughline_propagation():
    """Remove throughline propagation hooks installed by enable_*.

    Clears the provider and hook only if they are the ones we installed, so a
    user who registered their own provider/hook is left untouched.
    """
    if _client._call_opts_provider is _opts_provider:
        _client.set_call_opts_provider(None)
    if _server._call_context_hook is _context_hook:
        _server.set_call_context_hook(None)
