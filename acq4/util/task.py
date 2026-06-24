# acq4's Qt bridge over the gentletask concurrency library.

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from gentletask import (
    Event,
    MultiException,
    ManualTask,
    MultiTask,
    Queue,
    Empty,
    Stopped,
    Task,
    ThreadTask,
    WorkerThread,
    asynch,
    check_stop,
    raise_errors,
    current_task,
    poll,
    sleep,
    synch,
    task_chain,
    task_context,
    throughline,
    _TaskCore,  # base wait() with the result/exception logic
)

from acq4.util import Qt, ptime
from pyqtgraph import FeedbackButton

__all__ = [
    # Re-exported gentletask core so acq4 code has one import.
    "ThreadTask",
    "WorkerThread",
    "asynch",
    "synch",
    "Stopped",
    "sleep",
    "check_stop",
    "poll",
    "Queue",
    "Empty",
    "Event",
    "throughline",
    "current_task",
    "task_chain",
    "task_context",
    "Task",
    "ManualTask",
    "MultiTask",
    "MultiException",
    # acq4-side additions.
    "set_state",
    "raise_errors",
    "QtFriendlyTask",
    "ManualQtFriendlyTask",
    "GuiMultiTask",
    "MultiFuture",
    "asynch_with_qt_signals",
    "run_in_gui_thread",
    "task_in_gui_thread",
    "FutureButton",
]


# ---------------------------------------------------------------------------
# State free functions
# ---------------------------------------------------------------------------
#
# A task body simply calls set_state("measuring"); the call finds the running task via
# current_task() and, if that task carries state (e.g. a QtFriendlyTask), updates it — which emits
# sigStateChanged. Outside any task, or for a task that does not carry state, the call is a safe
# no-op.


def set_state(state: Any) -> None:
    """Set the current task's state, emitting its state-changed signal.

    No-op outside any task or when the running task does not carry state.
    """
    task = current_task()
    if task is not None and hasattr(task, "set_state"):
        task.set_state(state)


# ---------------------------------------------------------------------------
# Shared Qt machinery
# ---------------------------------------------------------------------------


class _QtTaskSignals(Qt.QObject):
    """QObject mixin carrying the Qt machinery shared by QtFriendlyTask and ManualQtFriendlyTask.

    Both classes are gentletask tasks that are also QObjects so GUI code can
    connect to completion and state-change signals. This mixin owns the parts
    that are identical between them: the two signals, the state slot + property,
    the internal finish callback that emits sigFinished, and the event-pumping
    branch of wait(updates=True).

    It is always the QObject base in the MRO. The concrete classes put their
    gentletask base first — QtFriendlyTask(ThreadTask, _QtTaskSignals) and
    ManualQtFriendlyTask(ManualTask, _QtTaskSignals) — so this mixin (hence QObject) sits
    last before object. PyQt's cooperative QObject.__init__ forwards down the
    MRO via super().__init__(); with QObject last, that forwarding reaches
    object harmlessly rather than landing on a gentletask __init__ that
    requires arguments. The metaclass resolves to QObject's sip.wrappertype
    (a subclass of type, which is the gentletask classes' metaclass), so the
    multiple inheritance is well-formed.
    """

    sigFinished = Qt.Signal(object)  # self
    sigStateChanged = Qt.Signal(object, object)  # self, state

    def _init_qt_signals(self) -> None:
        """Initialize the QObject half and pin its signal affinity to the GUI thread.

        Pinning matters because acq4 routinely creates tasks from inside running
        worker tasks; without it, a task built on a worker thread would inherit
        that thread's affinity, and its queued sigFinished / sigStateChanged
        would be delivered to a thread with no event loop — so connected slots
        would silently never fire. moveToThread is legal from the constructing
        thread because the object is parentless.
        """
        Qt.QObject.__init__(self)
        self._state: Any = None
        # Pin signal affinity to the GUI thread when there is one. Headless
        # contexts (e.g. the motion-planner tests) have no QApplication; there
        # the QObject simply stays on its creating thread and signals still work
        # via direct connection.
        app = Qt.QApplication.instance()
        if app is not None:
            self.moveToThread(app.thread())

    # -- state ---------------------------------------------------------------

    def setState(self, state: Any) -> None:
        """Set the state and emit sigStateChanged (safe from any thread)."""
        if state == self._state:
            return
        self._state = state
        self.sigStateChanged.emit(self, state)

    # -- completion ----------------------------------------------------------

    def _on_task_finished(self, result: Any, exc: Optional[BaseException]) -> None:
        if self._user_on_finish is not None:
            self._user_on_finish(result, exc)
        self.sigFinished.emit(self)

    # -- waiting -------------------------------------------------------------

    def _wait_pumping(self, timeout: Optional[float]) -> Any:
        """Block until done by pumping the Qt event loop, then return the result.

        Used by wait(updates=True) on both QtFriendlyTask and ManualQtFriendlyTask so a wait from
        the GUI thread does not freeze the UI.
        """
        start = ptime.time()
        while not self.is_done:
            if timeout is not None and ptime.time() > start + timeout:
                break
            Qt.QTest.qWait(1)

        # KNOWN DIVERGENCE from old Future semantics: on timeout the old
        # Future.wait raised Future.Timeout, whereas this bridge returns None.
        # This is deliberately left as-is for now and is to be reconciled
        # during call-site migration (the return-vs-raise decision is deferred).
        if not self.is_done:
            return None
        # Re-raise / return through the gentletask wait now that we know it is
        # done. _TaskCore.wait carries the result/exception logic; reaching it
        # via super() here would wrongly land on QObject (this mixin's base), so
        # call _TaskCore.wait directly against the concrete task instance.
        return _TaskCore.wait(self, 0)


# ---------------------------------------------------------------------------
# QtFriendlyTask
# ---------------------------------------------------------------------------


class QtFriendlyTask(ThreadTask, _QtTaskSignals):
    """A gentletask ThreadTask that is also a QObject, so GUI code can connect
    to its completion and state-change signals.

    The Qt signals, state slot, finish-emit hook, and event-pumping wait live in
    the _QtTaskSignals mixin (shared with ManualQtFriendlyTask); see its docstring for the
    multiple-inheritance ordering rationale (ThreadTask first keeps QObject last
    before object).

    Start contract: by default (start=True) the work thread launches at the end
    of __init__, which keeps call sites terse. Registering completion handling
    via add_finish_callback is ALWAYS race-free — the callback fires immediately
    if the task already finished. But catching completion through the
    sigFinished Qt *signal* connection is only race-free if you connect before
    the body can finish. For a FAST body where you connect to sigFinished, use
    the deterministic "construct → connect → start" pattern: pass start=False,
    connect your slots, then call .start() (inherited from ThreadTask, and
    idempotent). Otherwise the default auto-start is fine.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        args=(),
        kwargs: Optional[dict] = None,
        *,
        name: Optional[str] = None,
        detach: bool = False,
        on_finish: Optional[Callable[[Any, Optional[BaseException]], Any]] = None,
        start: bool = True,
    ) -> None:
        # Order matters. Initialize the QObject (and its C++ half), our own
        # state, and pin signal affinity first; then build the ThreadTask with
        # start=False so the work thread does NOT launch yet; then register the
        # internal finish callback; and only then launch.
        self._init_qt_signals()
        self._user_on_finish = on_finish

        # Build the underlying ThreadTask WITHOUT starting it, so we can finish
        # wiring up Qt before any work runs.
        ThreadTask.__init__(
            self,
            fn,
            args,
            kwargs,
            name=name,
            detach=detach,
            start=False,
        )

        # Register the internal finish callback that emits sigFinished. Done via
        # add_finish_callback (race-free) BEFORE starting, so the signal is
        # wired even if the body finishes the instant it starts. The callback
        # fires on the worker thread; the queued Qt connection then marshals
        # connected slots to the GUI thread, which is the intended behavior.
        self.add_finish_callback(self._on_task_finished)

        if start:
            self.start()

    # -- waiting -------------------------------------------------------------

    def wait(self, timeout: Optional[float] = None, updates: bool = False) -> Any:
        """Block until done, returning the result or re-raising the worker's error.

        When *updates* is True, pump the Qt event loop instead of parking on the
        gentletask condition, so a wait from the GUI thread does not freeze the
        UI. When *updates* is False, defer to the normal ThreadTask.wait, which
        preserves cooperative-stop propagation from a parent task.
        """
        if not updates:
            return super().wait(timeout)
        return self._wait_pumping(timeout)


def asynch_with_qt_signals(
    fn: Callable,
    name: Optional[str] = None,
    detach: bool = False,
    on_finish: Optional[Callable[[Any, Optional[BaseException]], Any]] = None,
) -> Callable[..., "QtFriendlyTask"]:
    """Like gentletask.asynch, but launches the work in a QtFriendlyTask (Qt signals).

    Plain ``asynch`` only builds a ThreadTask; use ``asynch_with_qt_signals`` when a
    function's result needs ``sigFinished``/``sigStateChanged``/``set_state`` so
    GUI code can connect to it. Calling the returned launcher starts a QtFriendlyTask
    immediately::

        @asynch_with_qt_signals
        def run_sequence(...):
            set_state("acquiring"); ...; return result

        task = run_sequence(...)            # a started QtFriendlyTask
        task.sigStateChanged.connect(...)

    ``synch(asynch_with_qt_signals(fn))`` de-wraps to run ``fn`` inline (via _asynch_wraps),
    exactly like ``synch`` on an ``asynch``-wrapped callable.
    """

    def wrapper(*args: Any, **kwargs: Any) -> "QtFriendlyTask":
        return QtFriendlyTask(fn, args, kwargs, name=name, detach=detach, on_finish=on_finish)

    # Record the original callable so synch() can de-wrap back to it.
    wrapper._asynch_wraps = fn
    return wrapper


# ---------------------------------------------------------------------------
# ManualQtFriendlyTask
# ---------------------------------------------------------------------------


class ManualQtFriendlyTask(ManualTask, _QtTaskSignals):
    """A gentletask ManualTask that is also a QObject, so GUI code can connect to
    its completion and state-change signals.

    ManualQtFriendlyTask is the externally-completed analog of QtFriendlyTask: it has no body and
    spawns no thread. An external producer (a hardware monitor thread, a socket
    reader, a GUI callback, a lock loop) completes it by calling resolve(),
    fail(), or stop(). Completion fires the internal finish callback, which emits
    sigFinished; a queued Qt connection then marshals connected slots to the GUI
    thread even when the producer calls resolve()/fail() from its own thread.

    State: because a ManualTask has no running body, the module-level free
    set_state() will NOT reach it (the producer is not running as this task's
    current_task()). The external producer therefore calls
    QtFriendlyTask.set_state(...) DIRECTLY. set_state/state/current_state come from
    the _QtTaskSignals mixin and behave exactly as on QtFriendlyTask.

    See _QtTaskSignals for the multiple-inheritance ordering rationale (ManualTask
    first keeps QObject last before object).
    """

    def __init__(
        self,
        name: Optional[str] = None,
        *,
        on_finish: Optional[Callable[[Any, Optional[BaseException]], Any]] = None,
    ) -> None:
        # Order matters and mirrors QtFriendlyTask. Initialize the QObject (and its C++
        # half), our own state, and pin signal affinity first; then build the
        # ManualTask (which registers with the parent task for stop-cascade and
        # spawns NO thread); then register the internal finish callback. There is
        # no start: a ManualTask has no body to launch.
        self._init_qt_signals()
        self._user_on_finish = on_finish

        # Do NOT forward on_finish to ManualTask.__init__: _on_task_finished invokes
        # self._user_on_finish itself (matching QtFriendlyTask), so forwarding it would
        # call the user callback twice.
        ManualTask.__init__(self, name=name)

        # Register the internal finish callback that emits sigFinished. Done via
        # add_finish_callback (race-free): it fires immediately if the promise is
        # already complete. The producer typically calls resolve()/fail() from a
        # non-GUI thread; the queued Qt connection then marshals connected slots
        # to the GUI thread.
        self.add_finish_callback(self._on_task_finished)

    def wait(self, timeout: Optional[float] = None, updates: bool = False) -> Any:
        """Block until completed, returning the resolved value or re-raising.

        When *updates* is True, pump the Qt event loop instead of parking on the
        gentletask condition, so a wait from the GUI thread does not freeze the
        UI while it blocks on an external producer. When *updates* is False,
        defer to the normal ManualTask.wait, which preserves cooperative-stop
        propagation from a parent task.
        """
        if not updates:
            return super().wait(timeout)
        return self._wait_pumping(timeout)


# ---------------------------------------------------------------------------
# GuiMultiTask
# ---------------------------------------------------------------------------


class GuiMultiTask(MultiTask, _QtTaskSignals):
    """A gentletask MultiTask that is also a QObject, so GUI code can connect to
    its completion and state-change signals.

    GuiMultiTask is the MultiTask analog of ManualQtFriendlyTask: it has no body and spawns
    no thread, completing when all of its child tasks complete. wait() returns
    the list of child results in order (or re-raises a lone child exception, or
    raises MultiException on several); stop() stops every child then itself.

    Beyond MultiTask, it re-emits each child's sigStateChanged as its own
    sigStateChanged, with the CHILD as sender (matching the old MultiFuture), so
    GUI code can watch a single aggregate for all the children's state updates.
    Children that are not Qt-backed (no sigStateChanged) are simply not relayed.

    Exposed under the name MultiFuture (see the alias below) to keep acq4's
    existing MultiFuture(futures, name=...) call sites unchanged.

    See _QtTaskSignals for the multiple-inheritance ordering rationale (MultiTask
    first keeps QObject last before object).
    """

    def __init__(self, tasks, name: Optional[str] = None) -> None:
        # Order mirrors ManualQtFriendlyTask. Initialize the QObject (and its C++ half),
        # our own state, and pin signal affinity first; then build the MultiTask
        # (which registers with the parent task for stop-cascade, wires each
        # child's finish callback, and spawns NO thread); then register the
        # internal finish callback. There is no start: a MultiTask has no body.
        self._init_qt_signals()
        self._user_on_finish = None

        MultiTask.__init__(self, tasks, name=name)

        # Register the internal finish callback that emits sigFinished. Done via
        # add_finish_callback (race-free): it fires immediately if every child is
        # already complete. The last child typically finishes on a worker thread;
        # the queued Qt connection then marshals connected slots to the GUI
        # thread.
        self.add_finish_callback(self._on_task_finished)

        # Re-emit each Qt-backed child's state changes as our own, with the child
        # as sender (matching the old MultiFuture). Children without a
        # sigStateChanged (plain ThreadTask, etc.) carry no Qt state to relay.
        for child in self.tasks:
            if hasattr(child, "sigStateChanged"):
                child.sigStateChanged.connect(self._relay_child_state)

    def _relay_child_state(self, child: Any, state: Any) -> None:
        self.sigStateChanged.emit(child, state)

    def percentDone(self) -> float:
        """Return the minimum percentDone across children (0.0 if none report)."""
        return min(
            (t.percentDone() for t in self.tasks if hasattr(t, "percentDone")),
            default=0.0,
        )

    def wait(self, timeout: Optional[float] = None, updates: bool = False) -> Any:
        """Block until all children complete, returning their results or raising.

        When *updates* is True, pump the Qt event loop instead of parking on the
        gentletask condition, so a wait from the GUI thread does not freeze the
        UI. When *updates* is False, defer to the normal MultiTask.wait, which
        preserves cooperative-stop propagation from a parent task.
        """
        if not updates:
            return super().wait(timeout)
        return self._wait_pumping(timeout)


# Expose under the name acq4 already uses at ~8 call sites: MultiFuture(futures,
# name=...). Keeping the alias avoids churning those sites during the migration.
MultiFuture = GuiMultiTask


# ---------------------------------------------------------------------------
# GUI-thread executor
# ---------------------------------------------------------------------------
#
# Ported from threadrun.ThreadCallFuture without depending on the old Future:
# a tiny QObject is moved to the target thread and a queued signal triggers the
# call there, so the function body runs in that thread's event loop.


class _GuiCall(Qt.QObject):
    """Marshals one function call onto a target thread's event loop."""

    sigRequestCall = Qt.Signal()

    def __init__(self, thread, fn, args, kwargs):
        Qt.QObject.__init__(self)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._result: Any = None
        self._exc: Optional[BaseException] = None
        # Plain threading.Event, NOT the stop-aware gentletask Event: this is the
        # call's own lifecycle signal, waited on from a (possibly already-stopped)
        # task. A gentletask Event would raise Stopped here when the calling task
        # has been cancelled — e.g. a FutureButton's stop firing the finish
        # callback that marshals back to the GUI thread.
        self._done = threading.Event()

        if thread is None:
            thread = Qt.QApplication.instance().thread()
        self.moveToThread(thread)
        self.sigRequestCall.connect(self._call_requested)
        self.sigRequestCall.emit()

    def _call_requested(self):
        try:
            self._result = self._fn(*self._args, **self._kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised to the caller
            self._exc = exc
        finally:
            self._done.set()

    def result(self):
        self._done.wait()
        if self._exc is not None:
            raise self._exc
        return self._result


def run_in_gui_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run *fn* in the GUI thread, block, and return its result.

    If already on the GUI thread, call *fn* inline.
    """
    gui_thread = Qt.QApplication.instance().thread()
    current = Qt.QtCore.QThread.currentThread()
    if gui_thread == current:
        return fn(*args, **kwargs)
    return _GuiCall(gui_thread, fn, args, kwargs).result()


def in_gui_thread(func):
    """Decorator to run a function in the GUI thread and return its result."""

    def run_func_in_gui_thread(*args, **kwds):
        return run_in_gui_thread(func, *args, **kwds)

    return run_func_in_gui_thread


def task_in_gui_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Task:
    """Return a QtFriendlyTask that runs *fn* in the GUI thread.

    The work itself is marshalled onto the GUI thread via run_in_gui_thread; the
    surrounding QtFriendlyTask gives callers a Task handle (wait/stop/signals) for it.
    """
    return QtFriendlyTask(lambda: run_in_gui_thread(fn, *args, **kwargs))


# ---------------------------------------------------------------------------
# FutureButton
# ---------------------------------------------------------------------------


class FutureButton(FeedbackButton):
    """A button that starts a gentletask Task when clicked and shows feedback
    based on the task's state.

    The name is kept as FutureButton to minimize call-site churn during the
    migration off the old Future.
    """

    sigFinished = Qt.Signal(object)  # task
    sigStateChanged = Qt.Signal(object, object)  # task, state

    def __init__(
        self,
        task_producer: Optional[Callable[[], Task]] = None,
        *args,
        stoppable: bool = False,
        success=None,
        failure=None,
        raiseOnError: bool = True,
        processing=None,
        showStatus: bool = True,
    ):
        """Create a new FutureButton.

        Parameters
        ----------
        task_producer : Callable[[], Task]
            A function that takes no arguments and returns a Task instance.
        *args
            Arguments to pass to FeedbackButton.__init__.
        stoppable : bool
            If True, the task can be stopped by clicking the button while it is
            in progress.
        success : str | None
            Message shown when the task completes successfully. Defaults to
            "Success".
        failure : str | None
            Message shown when the task fails. Defaults to the task's error.
        raiseOnError : bool
            If True, re-raise the task's exception (via wait) when it fails.
        processing : str | None
            Message shown while the task is in progress. Defaults to
            "Processing...".
        """
        super().__init__(*args)
        self._task = None
        self._task_producer = task_producer
        self._stoppable = stoppable
        self._userRequestedStop = False
        self._success = success
        self._raiseOnError = raiseOnError
        self._failure = failure
        self._processing = processing
        self._showStatus = showStatus
        self.clicked.connect(self._controlTheTask)

    def setOpts(self, **kwds):
        allowed_args = [
            "task_producer",
            "stoppable",
            "success",
            "failure",
            "processing",
            "showStatus",
            "raiseOnError",
        ]
        for k, v in kwds.items():
            if k not in allowed_args:
                raise NameError(f"Unknown option {k}")
            setattr(self, f"_{k}", v)

    def processing(self, message="Processing..", tip="", processEvents=True):
        """Displays specified message on button to let user know the action is in progress. Threadsafe."""
        # This had to be reimplemented to allow stoppable buttons to remain enabled.
        isGuiThread = (
            Qt.QtCore.QThread.currentThread() == Qt.QtCore.QCoreApplication.instance().thread()
        )
        if isGuiThread:
            self.setEnabled(self._stoppable)
            self.setText(message, temporary=True)
            self.setChecked(True)
            self.setToolTip(tip, temporary=True)
            self.setStyleSheet("background-color: #AFA; color: #000;", temporary=True)
            if processEvents:
                Qt.QtWidgets.QApplication.processEvents()
        else:
            self.sigCallProcess.emit(message, tip, processEvents)

    def _controlTheTask(self):
        if self._task is None:
            self.processing(
                self._processing
                or (f"Cancel {self.text()}" if self._stoppable else "Processing...")
            )
            try:
                task = self._task = self._task_producer()
            except Exception:
                self.failure("Error!")
                raise
            # Finish display is marshalled to the GUI thread: the finish callback
            # fires on the worker thread, so it routes through run_in_gui_thread.
            task.add_finish_callback(self._taskFinishedFromWorker)
            if isinstance(task, QtFriendlyTask):
                task.sigStateChanged.connect(self._taskStateChanged)
        else:
            self._userRequestedStop = True
            self._task.stop()

    def _taskFinishedFromWorker(self, result, exc):
        run_in_gui_thread(self._taskFinished, result, exc)

    def _taskFinished(self, result, exc):
        task = self._task
        if task is None:
            return
        self._task = None
        self.sigFinished.emit(task)
        if exc is None:
            self.success(self._success or "Success")
        elif self._userRequestedStop:
            self._userRequestedStop = False
            self.reset()
        elif isinstance(exc, Stopped):
            self.reset()
        else:
            self.failure(self._failure or (str(exc) or "Failed!")[:40])
            if self._raiseOnError:
                raise exc

    def _taskStateChanged(self, task, state):
        if self._showStatus:
            self.setText(str(state), temporary=True)
        self.sigStateChanged.emit(task, state)
