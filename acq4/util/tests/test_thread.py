"""Unit tests for acq4.util.Thread: the QThread wrapper's run() dispatch.

These cover the wrapper's debugging aids (thread naming, faulthandler setup) being
unable to stop the subclass's run() from executing.
"""

import contextlib
import io

from acq4.util.Thread import Thread


class RecordingThread(Thread):
    def __init__(self, **kwds):
        Thread.__init__(self, **kwds)
        self.ran = False

    def run(self):
        self.ran = True


def test_run_executes_when_faulthandler_setup_fails(monkeypatch):
    monkeypatch.setattr(
        "acq4.util.Thread.enableFaulthandler",
        lambda: (_ for _ in ()).throw(io.UnsupportedOperation("fileno")),
    )
    thread = RecordingThread(name="recording")
    thread.run()
    assert thread.ran


def test_started_thread_runs_while_stderr_is_captured(qapp):
    """A thread started while sys.stderr is a StringIO still runs its body.

    faulthandler.enable() needs sys.stderr.fileno(); a capture buffer without one
    must not take the thread's run() down with it.
    """
    thread = RecordingThread(name="recording")
    with contextlib.redirect_stderr(io.StringIO()):
        thread.start()
        assert thread.wait(5000)
    assert thread.ran


def test_faulthandler_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(
        "acq4.util.Thread.enableFaulthandler",
        lambda: (_ for _ in ()).throw(io.UnsupportedOperation("fileno")),
    )
    thread = RecordingThread(name="recording")
    with caplog.at_level("ERROR", logger="acq4"):
        thread.run()
    assert "faulthandler" in caplog.text
    assert "recording" in caplog.text
