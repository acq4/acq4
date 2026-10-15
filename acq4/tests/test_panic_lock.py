"""Panic Lock tests — ``GlobalHalt`` in isolation (see ``Panic Lock Spec.md`` §13).

Mock callables only: no hardware, no devices, no Manager. This file covers the
"State model", "Latch ordering", "Fan-out", "Exception propagation" sections of
§13, and the panic-dialog bullets -- the dialog is driven entirely by a
``GlobalHalt``, so it needs no more than a mock participant and a ``qtbot``.
The "Guards" and "Integration" sections live elsewhere.
"""

import contextlib
import threading
import time

import pytest

from acq4.panic import GlobalHalt, GlobalHaltException
from acq4.util import Qt
from acq4.util.PanicDialog import PanicDialogController
from acq4.util.task import Stopped, asynch

# Generous: these waits only ever gate a pass, never manufacture one. A healthy
# fan-out completes in milliseconds.
TIMEOUT = 5.0

# Long enough for a spurious extra invocation (or a task the fan-out should never
# have started) to land, short enough not to drag the suite out. Used only for
# assertions of the form "this must NOT happen".
SETTLE = 0.2


class RecordingCallback:
    """A no-argument callable standing in for a participant's ``abort()``.

    Records how many times it ran, optionally runs *before* work inside the
    callback, optionally blocks on a *gate* event, and optionally raises.
    """

    def __init__(self, name="cb", raises=None, gate=None, before=None):
        self.name = name
        self.count = 0
        self.raises = raises
        self.gate = gate
        self.before = before
        self.entered = threading.Event()
        self._counted = threading.Condition()

    def __call__(self):
        with self._counted:
            self.count += 1
            self._counted.notify_all()
        self.entered.set()
        if self.before is not None:
            self.before()
        if self.gate is not None and not self.gate.wait(TIMEOUT):
            raise AssertionError(f"{self.name}: gate never released")
        if self.raises is not None:
            raise self.raises

    def wait_for_count(self, n, timeout=TIMEOUT):
        with self._counted:
            return self._counted.wait_for(lambda: self.count >= n, timeout)


def wait_until(predicate, timeout=TIMEOUT, interval=0.01):
    """Poll *predicate* until it returns something truthy; return it, or None."""
    deadline = time.perf_counter() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.perf_counter() >= deadline:
            return None
        time.sleep(interval)


@contextlib.contextmanager
def captured_thread_exceptions():
    """Collect what ``raise_errors`` reports.

    ``raise_errors`` re-raises on a daemon monitor thread so the failure reaches
    the process's unhandled-exception hook, not the caller. Swap that hook out to
    see it -- and to keep deliberate failures out of the suite's stderr.

    Reports from an *earlier* test's monitor thread can still land here, so
    callers must match on the task name rather than assuming the list is theirs.
    """
    records = []
    lock = threading.Lock()
    original = threading.excepthook

    def hook(args):
        with lock:
            records.append(args)

    threading.excepthook = hook
    try:
        yield records
    finally:
        threading.excepthook = original


def reported(records, task_name):
    """The captured reports naming *task_name*, newest last."""
    return [r for r in list(records) if task_name in str(r.exc_value)]


@pytest.fixture
def gh():
    """A fresh, ARMED GlobalHalt for each test."""
    return GlobalHalt()


@pytest.fixture
def panic_ui(qtbot, gh):
    """A `PanicDialogController` watching *gh*, cleaned up afterwards.

    Teardown cannot go through `close()`: the dialog refuses it (§9.1). It goes
    through `dismiss()`, the one sanctioned exit, so a test that leaves the
    dialog up does not leak a window into the next one.
    """
    controller = PanicDialogController(gh)
    yield controller
    dialog = controller.dialog
    if dialog is not None:
        dialog.dismiss()
        dialog.deleteLater()


def show_dialog(qtbot, gh, panic_ui, reason="something went wrong"):
    """Halt and return the dialog, exposed and ready for interaction."""
    gh.halt(reason)
    dialog = panic_ui.dialog
    assert dialog is not None, "halt() did not produce a dialog"
    qtbot.addWidget(dialog)
    qtbot.waitUntil(dialog.isVisible, timeout=int(TIMEOUT * 1000))
    return dialog


# ---------------------------------------------------------------------------
# §13 State model
# ---------------------------------------------------------------------------


def test_halt_sets_state_resume_clears_it_and_signals_fire_once(gh):
    seen = []
    gh.sigPanicStateChanged.connect(seen.append)

    assert gh.halted is False
    assert gh.reason is None

    gh.halt("smoke alarm")
    assert gh.halted is True
    assert gh.reason == "smoke alarm"

    gh.resume()
    assert gh.halted is False
    assert gh.reason is None

    assert seen == ["smoke alarm", None]


def test_default_halt_reason(gh):
    gh.halt()
    assert gh.reason == "User pressed ESC"


def test_repeat_halt_reruns_fanout_and_retains_the_original_reason(gh):
    cb = RecordingCallback("counter")
    gh.add_abort_callback(cb, name="counter")
    seen = []
    gh.sigPanicStateChanged.connect(seen.append)

    gh.halt("first reason")
    assert cb.wait_for_count(1)

    gh.halt("second reason")
    assert cb.wait_for_count(2), "a repeat halt must re-run the fan-out"

    assert gh.halted is True
    assert gh.reason == "first reason", "reason is recorded only on ARMED -> HALTED"
    assert seen == ["first reason"], "no state change, so no second signal"


def test_sigHaltRequested_fires_on_every_halt_and_state_changed_only_on_transition(gh):
    """§9.1: the dialog rides on sigHaltRequested precisely because a repeat
    halt changes no state -- a second ESC press means "I mean it" and must still
    put the dialog in front of the operator."""
    requested = []
    changed = []
    gh.sigHaltRequested.connect(lambda: requested.append(len(requested)))
    gh.sigPanicStateChanged.connect(changed.append)

    gh.halt("first")
    assert len(requested) == 1
    assert changed == ["first"]

    gh.halt("second")
    gh.halt("third")
    assert len(requested) == 3, "every halt() must request the dialog"
    assert changed == ["first"], "no transition, so no state-change signal"

    gh.resume()
    assert len(requested) == 3, "resume() is not a halt request"
    assert changed == ["first", None]

    gh.halt("after resume")
    assert len(requested) == 4
    assert changed == ["first", None, "after resume"]


def test_resume_while_armed_is_a_noop(gh):
    seen = []
    gh.sigPanicStateChanged.connect(seen.append)

    gh.resume()

    assert gh.halted is False
    assert gh.reason is None
    assert seen == []


def test_check_raises_only_while_halted_and_carries_the_reason(gh):
    gh.check()  # armed: no raise

    gh.halt("bad things")
    with pytest.raises(GlobalHaltException) as exc_info:
        gh.check()
    assert "bad things" in str(exc_info.value)

    gh.resume()
    gh.check()


# ---------------------------------------------------------------------------
# §13 Latch ordering
# ---------------------------------------------------------------------------


def test_halted_is_observable_from_another_thread_before_the_first_callback_runs(gh):
    """A device commanded from another thread mid-fan-out must be refused.

    The first abort callback blocks, so the observer thread reads the state
    while the fan-out is still in progress -- exactly the window §3 says must
    never exist.
    """
    proceed = threading.Event()
    first_started = threading.Event()
    observed = {}

    def first_callback():
        observed["in_callback_thread"] = gh.halted
        first_started.set()
        proceed.wait(TIMEOUT)

    gh.add_abort_callback(first_callback, name="first")

    def observer():
        if not first_started.wait(TIMEOUT):
            return
        observed["in_other_thread"] = gh.halted
        observed["reason_in_other_thread"] = gh.reason
        try:
            gh.check()
        except GlobalHaltException as exc:
            observed["check_raised"] = exc

    watcher = threading.Thread(target=observer, name="panic-observer")
    watcher.start()
    try:
        gh.halt("latch ordering")
        assert first_started.wait(TIMEOUT), "the first abort callback never ran"
    finally:
        proceed.set()
        watcher.join(TIMEOUT)

    assert observed["in_callback_thread"] is True
    assert observed["in_other_thread"] is True
    assert observed["reason_in_other_thread"] == "latch ordering"
    assert isinstance(observed.get("check_raised"), GlobalHaltException)


# ---------------------------------------------------------------------------
# §13 Fan-out
# ---------------------------------------------------------------------------


def test_every_registered_callback_is_invoked_exactly_once_per_halt(gh):
    cbs = [RecordingCallback(f"cb{i}") for i in range(3)]
    for cb in cbs:
        gh.add_abort_callback(cb, name=cb.name)

    gh.halt("first")
    for cb in cbs:
        assert cb.wait_for_count(1), f"{cb.name} never ran"

    gh.halt("second")
    for cb in cbs:
        assert cb.wait_for_count(2), f"{cb.name} did not re-run"

    time.sleep(SETTLE)
    for cb in cbs:
        assert cb.count == 2, f"{cb.name} ran {cb.count} times, expected 2"


def test_duplicate_registration_is_a_noop(gh):
    cb = RecordingCallback("dup")
    gh.add_abort_callback(cb, name="dup")
    gh.add_abort_callback(cb, name="dup-again")

    gh.halt("dup")
    assert cb.wait_for_count(1)
    time.sleep(SETTLE)
    assert cb.count == 1, "a callback registered twice must run only once"


def test_registering_while_halted_does_not_invoke_the_callback(gh):
    gh.halt("already halted")
    late = RecordingCallback("late")
    gh.add_abort_callback(late, name="late")

    time.sleep(SETTLE)
    assert late.count == 0, "registration must not invoke cb, even while halted"

    gh.halt("halted again")
    assert late.wait_for_count(1), "but it does take part in the next fan-out"


def test_a_removed_callback_is_not_invoked_on_a_subsequent_halt(gh):
    kept = RecordingCallback("kept")
    dropped = RecordingCallback("dropped")
    gh.add_abort_callback(kept, name="kept")
    gh.add_abort_callback(dropped, name="dropped")

    gh.halt("before removal")
    assert kept.wait_for_count(1)
    assert dropped.wait_for_count(1)

    gh.remove_abort_callback(dropped)
    gh.halt("after removal")
    assert kept.wait_for_count(2)

    time.sleep(SETTLE)
    assert dropped.count == 1


def test_removing_an_unregistered_callback_is_silent(gh):
    gh.remove_abort_callback(RecordingCallback("never registered"))
    gh.remove_abort_callback(lambda: None)


def test_registering_or_removing_inside_a_callback_does_not_disturb_the_fanout(gh):
    """Snapshot semantics (§11): a callback removed during the fan-out runs
    anyway if it was already snapshotted; one registered during the fan-out does
    not run until the next halt."""
    late = RecordingCallback("late")
    doomed = RecordingCallback("doomed")

    def mutate():
        gh.remove_abort_callback(doomed)
        gh.add_abort_callback(late, name="late")

    mutator = RecordingCallback("mutator", before=mutate)
    gh.add_abort_callback(mutator, name="mutator")
    gh.add_abort_callback(doomed, name="doomed")

    gh.halt("snapshot")
    assert mutator.wait_for_count(1)
    assert doomed.wait_for_count(1), "already snapshotted, so it runs anyway"

    time.sleep(SETTLE)
    assert late.count == 0, "registered mid-fan-out, so not part of this sweep"

    gh.halt("snapshot again")
    assert late.wait_for_count(1)
    assert mutator.wait_for_count(2)
    time.sleep(SETTLE)
    assert doomed.count == 1, "removed, so never again"


def test_a_raising_callback_does_not_prevent_others_and_is_reported(gh):
    boom = RecordingCallback("boom", raises=RuntimeError("driver exploded"))
    ok1 = RecordingCallback("ok1")
    ok2 = RecordingCallback("ok2")
    for cb in (ok1, boom, ok2):
        gh.add_abort_callback(cb, name=cb.name)

    with captured_thread_exceptions() as records:
        gh.halt("raising callback")

        assert ok1.wait_for_count(1)
        assert ok2.wait_for_count(1)
        assert boom.wait_for_count(1)

        hits = wait_until(lambda: reported(records, "abort(boom)"))

    assert hits, "raise_errors did not surface the failing abort callback"
    assert "driver exploded" in str(hits[-1].exc_value)
    assert isinstance(hits[-1].exc_value.__cause__, RuntimeError)


def test_a_hanging_callback_blocks_neither_the_fanout_nor_the_others(gh):
    gate = threading.Event()
    hang = RecordingCallback("hang", gate=gate)
    ok = RecordingCallback("ok")
    gh.add_abort_callback(hang, name="hang")
    gh.add_abort_callback(ok, name="ok")

    try:
        start = time.perf_counter()
        gh.halt("hanging callback")
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"_fanOut() blocked for {elapsed:.2f}s"
        assert hang.entered.wait(TIMEOUT), "the hanging callback never started"
        assert ok.wait_for_count(1), "a hung participant stalled the sweep"
        assert gh.halted is True
    finally:
        gate.set()


# ---------------------------------------------------------------------------
# §13 Exception propagation
# ---------------------------------------------------------------------------


def test_global_halt_exception_is_not_a_stopped():
    assert issubclass(GlobalHaltException, Exception)
    assert not issubclass(GlobalHaltException, Stopped)

    outcome = None
    try:
        try:
            raise GlobalHaltException("halted")
        except Stopped:  # pragma: no cover - must not be reached
            outcome = "swallowed as cancellation"
    except GlobalHaltException:
        outcome = "propagated"
    assert outcome == "propagated"


def test_global_halt_exception_propagates_out_of_asynch():
    def raiser():
        raise GlobalHaltException("halted from a task")

    task = asynch(raiser, name="halt-propagation")()
    with pytest.raises(GlobalHaltException) as exc_info:
        task.wait(TIMEOUT)
    assert "halted from a task" in str(exc_info.value)


def test_an_abort_callback_that_trips_its_own_guard_is_reported_not_swallowed(gh):
    """§6.3: `GlobalHaltException` is not a `Stopped`, so `raise_errors` reports
    a self-inflicted guard trip inside the fan-out instead of exempting it."""
    tripwire = RecordingCallback(
        "tripwire", raises=GlobalHaltException("guard tripped by the halt path")
    )
    gh.add_abort_callback(tripwire, name="self-tripping-guard")

    with captured_thread_exceptions() as records:
        gh.halt("self trip")
        assert tripwire.wait_for_count(1)
        hits = wait_until(lambda: reported(records, "abort(self-tripping-guard)"))

    assert hits, "a GlobalHaltException in the fan-out was swallowed"
    record = hits[-1]
    assert "guard tripped by the halt path" in str(record.exc_value)
    assert isinstance(record.exc_value.__cause__, GlobalHaltException)


# ---------------------------------------------------------------------------
# §13 Panic dialog (§9.1)
# ---------------------------------------------------------------------------


def test_the_dialog_shows_the_headline_and_the_reason(qtbot, gh, panic_ui):
    dialog = show_dialog(qtbot, gh, panic_ui, reason="stage ran into the objective")

    assert dialog.headlineLabel.text() == "ALL DEVICES HALTED"
    assert dialog.reasonLabel.text() == "stage ran into the objective"
    assert dialog.resumeBtn.text() == "Resume"
    assert dialog.isModal() is False, "§9.1: modeless with respect to the event loop"


def test_the_dialog_appears_after_the_abort_tasks_are_started_and_a_hang_does_not_delay_it(
    qtbot, gh, panic_ui
):
    """§9.1: "after invoking" means after every abort task has been *started*.

    ``_fanOut()`` is fire-and-forget (§5.3), so the ordering that matters is
    fan-out-then-dialog, and a participant that blocks forever inside its abort
    callback must not hold the operator's only way out hostage.
    """
    order = []
    gate = threading.Event()
    hang = RecordingCallback("hang", gate=gate)
    gh.add_abort_callback(hang, name="hang")

    realFanOut = gh._fanOut

    def recordingFanOut():
        realFanOut()
        order.append("abort tasks started")

    gh._fanOut = recordingFanOut
    # Connected after the controller, so it runs immediately after the slot that
    # shows the dialog and can report whether the dialog was up by then.
    gh.sigHaltRequested.connect(
        lambda: order.append(("dialog visible", panic_ui.dialog.isVisible()))
    )

    try:
        start = time.perf_counter()
        gh.halt("hung device")
        elapsed = time.perf_counter() - start

        assert hang.entered.wait(TIMEOUT), "the abort task never started"
        assert elapsed < 1.0, f"halt() took {elapsed:.2f}s with one hung participant"
        assert order == ["abort tasks started", ("dialog visible", True)]
    finally:
        gate.set()
        if panic_ui.dialog is not None:
            qtbot.addWidget(panic_ui.dialog)


def test_a_repeat_halt_reraises_and_reactivates_the_dialog(qtbot, gh, panic_ui, monkeypatch):
    """§11: a repeat halt changes no state, but the dialog is still re-raised
    and re-activated -- otherwise a second ESC press would look like nothing."""
    dialog = show_dialog(qtbot, gh, panic_ui, reason="first reason")

    calls = []
    monkeypatch.setattr(dialog, "raise_", lambda: calls.append("raise"))
    monkeypatch.setattr(dialog, "activateWindow", lambda: calls.append("activate"))
    changed = []
    gh.sigPanicStateChanged.connect(changed.append)

    gh.halt("second reason")

    assert calls == ["raise", "activate"], "a repeat halt must re-raise and re-activate"
    assert changed == [], "no state change, so nothing rode on sigPanicStateChanged"
    assert dialog.isVisible()
    assert dialog.reasonLabel.text() == "first reason", "§3: the original reason survives"


def test_escape_does_not_dismiss_the_dialog(qtbot, gh, panic_ui):
    """§9.1: ESC is the panic key. QDialog maps it to reject() by default."""
    dialog = show_dialog(qtbot, gh, panic_ui)

    qtbot.keyClick(dialog, Qt.Qt.Key_Escape)
    assert dialog.isVisible(), "ESC dismissed the panic dialog"
    assert gh.halted is True


def test_the_dialog_cannot_be_closed_except_by_resume(qtbot, gh, panic_ui):
    """No title-bar X, no Alt+F4, no close(), no reject() (§9.1)."""
    dialog = show_dialog(qtbot, gh, panic_ui)

    assert not (dialog.windowFlags() & Qt.Qt.WindowCloseButtonHint), "title bar has an X"

    dialog.reject()
    assert dialog.isVisible(), "reject() dismissed the dialog"

    dialog.close()
    assert dialog.isVisible(), "close() dismissed the dialog"

    # Alt+F4 arrives as a plain close event -- the same door close() uses.
    Qt.QApplication.instance().sendEvent(dialog, Qt.QCloseEvent())
    assert dialog.isVisible(), "a close event dismissed the dialog"

    assert gh.halted is True


def test_the_esc_shortcut_still_panics_while_the_dialog_holds_focus(qtbot, gh, panic_ui):
    """An application-scoped ESC QShortcut (§4) must reach halt() past the dialog.

    Qt dispatches QEvent.Shortcut ahead of the key press, so the shortcut takes
    the key before the dialog's own handler ever sees it. The key is delivered
    to the QWindow, not the QWidget, because only that path runs the shortcut
    map -- QTest's widget overload posts straight to the widget and would test
    nothing.
    """
    host = Qt.QWidget()
    qtbot.addWidget(host)
    shortcut = Qt.QShortcut(Qt.QKeySequence("Esc"), host)
    shortcut.setContext(Qt.Qt.ApplicationShortcut)
    halts = []

    def onEsc():
        halts.append("esc")
        gh.halt("User pressed ESC")

    shortcut.activated.connect(onEsc)
    host.show()
    qtbot.waitUntil(host.isVisible, timeout=int(TIMEOUT * 1000))

    dialog = show_dialog(qtbot, gh, panic_ui, reason="first reason")
    dialog.raise_()
    dialog.activateWindow()
    if dialog.windowHandle() is not None:
        dialog.windowHandle().requestActivate()
    # Qt's shortcut context matcher refuses every shortcut while the application
    # has no active window at all, so this needs a real one. It does not need
    # the *dialog* to be the active one: an ApplicationShortcut matches on its
    # host widget being visible and unblocked.
    try:
        qtbot.waitUntil(
            lambda: dialog.windowHandle() is not None
            and Qt.QApplication.instance().activeWindow() is not None,
            timeout=int(TIMEOUT * 1000),
        )
    except Exception:
        pytest.skip("no window activation available in this environment")

    qtbot.keyClick(dialog.windowHandle(), Qt.Qt.Key_Escape)
    qtbot.waitUntil(lambda: len(halts) == 1, timeout=int(TIMEOUT * 1000))

    assert dialog.isVisible(), "ESC closed the dialog instead of panicking again"
    assert gh.halted is True
    assert gh.reason == "first reason", "§3: a repeat halt keeps the original reason"


def test_resume_clears_the_latch_the_dialog_goes_away_and_guards_pass_again(
    qtbot, gh, panic_ui
):
    """§8: Resume clears the latch and nothing else."""
    dialog = show_dialog(qtbot, gh, panic_ui, reason="operator hit ESC")
    with pytest.raises(GlobalHaltException):
        gh.check()

    qtbot.mouseClick(dialog.resumeBtn, Qt.Qt.LeftButton)

    assert gh.halted is False
    assert gh.reason is None
    assert not dialog.isVisible(), "the dialog outlived the halt"
    gh.check()  # guarded operations work again

    # ...and the same dialog comes back on the next halt.
    gh.halt("again")
    assert dialog.isVisible()
    assert panic_ui.dialog is dialog


def test_a_programmatic_resume_also_takes_the_dialog_down(qtbot, gh, panic_ui):
    dialog = show_dialog(qtbot, gh, panic_ui)
    gh.resume()
    assert not dialog.isVisible()


def test_a_halt_from_a_worker_thread_builds_and_shows_the_dialog_on_the_gui_thread(
    qtbot, gh, panic_ui
):
    """§5c: halt() may come from any device thread; the widget may not.

    The controller has GUI-thread affinity and the connection is left at
    AutoConnection, so the emission is queued rather than run on the device
    thread -- and halt() returns without waiting for it.
    """
    guiThread = Qt.QApplication.instance().thread()
    worker = threading.Thread(target=lambda: gh.halt("worker thread"), name="panic-worker")
    worker.start()
    worker.join(TIMEOUT)
    assert not worker.is_alive(), "halt() blocked on the GUI thread"

    # This thread is the GUI thread and has not run its event loop since, so the
    # queued call cannot have been delivered yet.
    assert panic_ui.dialog is None

    qtbot.waitUntil(
        lambda: panic_ui.dialog is not None and panic_ui.dialog.isVisible(),
        timeout=int(TIMEOUT * 1000),
    )
    qtbot.addWidget(panic_ui.dialog)
    assert panic_ui.dialog.thread() == guiThread
    assert panic_ui.dialog.reasonLabel.text() == "worker thread"
