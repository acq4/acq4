"""Orchestrator: runs a Protocol over a queue of cells, serially, routing on each
action's outcome and converting flow signals / exceptional states into control."""
from __future__ import annotations

from collections import deque

from acq4.util import Qt
from acq4.util.task import Stopped, Event, check_stop

from .context import ExecutionContext
from .exceptions import (
    OrchestrationError,
    AdvanceToNextCell,
    RetryCurrentCell,
    AbortExperiment,
)


class Orchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)                 # "running"/"waiting"/"paused"/"error"
    sigCurrentAction = Qt.Signal(object, object)   # cell, action (None,None when idle)
    sigCellFinished = Qt.Signal(object, str)   # cell, status

    def __init__(self, protocol, manager=None, contextFactory=None):
        Qt.QObject.__init__(self)
        self.protocol = protocol
        self.manager = manager
        self._queue = deque()
        self._pauseEvent = Event()
        self._pauseEvent.set()  # set == running
        self._nextCellRequested = False
        self._contextFactory = contextFactory or self._defaultContext

    # ---- queue / context ----
    def enqueue(self, cell):
        self._queue.append(cell)

    def _defaultContext(self, cell) -> ExecutionContext:
        return ExecutionContext(cell=cell, manager=self.manager)

    # ---- test / headless entry points ----
    def run_sync_cell(self, cell):
        """Run a single cell through the protocol inline. Used by tests/headless."""
        self._nextCellRequested = False
        self._processCell(cell)

    # ---- graph walk ----
    def _checkPause(self):
        if not self._pauseEvent.is_set():
            self.sigStatus.emit("paused")
            self._pauseEvent.wait()
            self.sigStatus.emit("running")

    def _runAction(self, action, ctx) -> str:
        try:
            result = action.run(ctx)
        except Stopped:
            action.safeAbort(ctx)
            raise
        if result not in action.outcomes:
            raise ValueError(
                f"{action.name} returned unknown outcome {result!r}; "
                f"expected one of {action.outcomes}"
            )
        return result

    def _walk(self, cell, protocol, node_id):
        """Walk `protocol` from `node_id`, routing on outcomes. Raises FlowSignal
        or OrchestrationError up to the caller."""
        while node_id is not None:
            self._checkPause()
            check_stop()
            if self._nextCellRequested:
                raise AdvanceToNextCell("next cell requested")
            action = protocol.nodes[node_id]
            ctx = self._contextFactory(cell)
            self.sigCurrentAction.emit(cell, action)
            outcome = self._runAction(action, ctx)
            node_id = protocol.next_node(node_id, outcome)

    def _processCell(self, cell):
        """Run the main protocol for one cell (no exception handling yet)."""
        self._walk(cell, self.protocol, self.protocol.entry)
        self.sigCellFinished.emit(cell, "done")
