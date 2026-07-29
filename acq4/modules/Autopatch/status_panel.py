"""StatusPanel: Area 3's global controls (Start/Stop/Pause/Next) and the big
Running/Waiting/Paused/Error status indicator bound to an Orchestrator."""
from __future__ import annotations

from acq4.util import Qt


class StatusPanel(Qt.QWidget):
    # Emitted whenever the bound orchestrator's status changes, True while a
    # run is "running" or "paused". Area 4 (the protocol picker/Load/Reload)
    # listens to this to gate itself, rather than the window connecting
    # directly to the orchestrator's own sigStatus -- that would give the
    # orchestrator a live reference back to the window for as long as it
    # exists, exactly the kind of cycle bindOrchestrator/unbindOrchestrator
    # are already careful to avoid.
    sigInteractionLocked = Qt.Signal(bool)

    def __init__(self):
        super().__init__()
        self._orchestrator = None
        self._entrySource = None
        self._onStart = None
        # None stands for "no status yet reported" -- same button gating as the
        # orchestrator's own post-run "waiting" (see _updateButtons()).
        self._currentStatus = None

        self.startBtn = Qt.QPushButton("Start")
        self.stopBtn = Qt.QPushButton("Stop")
        self.pauseBtn = Qt.QPushButton("Pause")
        self.nextBtn = Qt.QPushButton("Next cell")

        self.statusLabel = Qt.QLabel("idle")
        self.statusLabel.setStyleSheet("font-size: 20pt; font-weight: bold;")
        self.currentActionLabel = Qt.QLabel("")
        self.currentActionLabel.setAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignVCenter)
        self.instructionLabel = Qt.QLabel("")
        self.instructionLabel.setStyleSheet("color: red; font-weight: bold;")
        self.instructionLabel.setVisible(False)

        # First row: the big status indicator on the left, the current-action
        # message pushed to the far right by the stretch between them.
        statusRow = Qt.QHBoxLayout()
        statusRow.addWidget(self.statusLabel)
        statusRow.addStretch()
        statusRow.addWidget(self.currentActionLabel)

        btnRow = Qt.QHBoxLayout()
        for b in (self.startBtn, self.stopBtn, self.pauseBtn, self.nextBtn):
            btnRow.addWidget(b)

        layout = Qt.QVBoxLayout()
        layout.addLayout(statusRow)
        layout.addLayout(btnRow)
        layout.addWidget(self.instructionLabel)
        self.setLayout(layout)

        # No protocol is bound yet, so every action button starts disabled.
        self._updateButtons()

    def bindOrchestrator(self, orchestrator, entrySource, onStart=None) -> None:
        """Bind Start/Stop/Pause/Next to `orchestrator`.

        `entrySource` is anything exposing `sigActionEntry(cell, entry, phase)`
        (CellPanel, in practice) -- the current-action label's text comes from
        that cell-bound ctx.log_action() entry stream (name + status) rather
        than from the orchestrator directly, since the orchestrator itself no
        longer knows about individual actions.

        `onStart`, if given, is called on the GUI thread when Start is clicked,
        before `orchestrator.start()` -- the seam a caller uses to snapshot any
        GUI-thread-only state (e.g. the selected pipette) before the
        orchestrator's worker thread begins running.
        """
        if self._orchestrator is not None:
            self.unbindOrchestrator()

        self._orchestrator = orchestrator
        self._entrySource = entrySource
        self._onStart = onStart
        # A freshly bound orchestrator hasn't reported a status yet -- treat it
        # the same as "waiting" so Start is enabled and Stop/Pause/Next are not.
        self._currentStatus = None
        self.startBtn.clicked.connect(self._onStartClicked)
        self.stopBtn.clicked.connect(orchestrator.stop)
        self.pauseBtn.clicked.connect(self._onPauseClicked)
        self.nextBtn.clicked.connect(orchestrator.requestNextCell)
        orchestrator.sigStatus.connect(self._onStatus)
        orchestrator.sigCurrentCell.connect(self._onCurrentCell)
        entrySource.sigActionEntry.connect(self._onActionEntry)
        self._updateButtons()

    def unbindOrchestrator(self) -> None:
        """Disconnect everything bindOrchestrator() connected to the currently
        bound orchestrator (and entry source), and drop both references.

        Shared by bindOrchestrator() (rebinding to a freshly loaded protocol)
        and window teardown (on module/window close), so both paths sever the
        panel<->orchestrator signal wiring the same way -- leaving no dangling
        Qt connection either way.
        """
        if self._orchestrator is None:
            return
        Qt.disconnect(self.startBtn.clicked, self._onStartClicked)
        Qt.disconnect(self.stopBtn.clicked, self._orchestrator.stop)
        Qt.disconnect(self.pauseBtn.clicked, self._onPauseClicked)
        Qt.disconnect(self.nextBtn.clicked, self._orchestrator.requestNextCell)
        Qt.disconnect(self._orchestrator.sigStatus, self._onStatus)
        Qt.disconnect(self._orchestrator.sigCurrentCell, self._onCurrentCell)
        Qt.disconnect(self._entrySource.sigActionEntry, self._onActionEntry)
        self._orchestrator = None
        self._entrySource = None
        self._onStart = None
        self._currentStatus = None
        self._updateButtons()
        self.sigInteractionLocked.emit(False)

    def _onStartClicked(self) -> None:
        if self._onStart is not None:
            self._onStart()
        self._orchestrator.start()

    def _onPauseClicked(self) -> None:
        # Toggle: Pause while running, Resume while paused -- see _updateButtons()
        # for the matching label swap.
        if self._currentStatus == "paused":
            self._orchestrator.resume()
        else:
            self._orchestrator.pause()

    def _onStatus(self, status: str) -> None:
        self.statusLabel.setText(status)
        self.instructionLabel.setVisible(status == "error")
        self._currentStatus = status
        self._updateButtons()
        self.sigInteractionLocked.emit(status in ("running", "paused"))

    def _onCurrentCell(self, cell) -> None:
        # sigCurrentCell(None) fires once the orchestrator's queue drains (see
        # Orchestrator._runLoopBody's finally). But the orchestrator can also
        # advance directly from one cell to the next with no None in between,
        # and the new cell's protocol may open no log_action at all -- so the
        # label must clear on every transition, not just the final None, or it
        # would keep showing the previous cell's last action. Any further live
        # content comes from _onActionEntry() below.
        self.currentActionLabel.setText("")

    def _onActionEntry(self, cell, entry, phase: str) -> None:
        if phase == "started":
            self.currentActionLabel.setText(f"{entry.name} — {cell!r}")
        elif phase == "status":
            self.currentActionLabel.setText(f"{entry.name} ({entry.status}) — {cell!r}")

    def _updateButtons(self) -> None:
        """Gate Start/Stop/Pause/Next on whether a protocol is loaded (an
        orchestrator is bound) and the orchestrator's last-reported status.

        No protocol bound: everything disabled. Otherwise: "waiting" (or no
        status yet, i.e. freshly bound and not yet started) enables only
        Start; "running" enables Stop/Pause/Next; "paused" enables Stop/Pause
        (relabeled "Resume") but not Next; "error" enables only Stop.
        """
        hasProtocol = self._orchestrator is not None
        status = self._currentStatus
        if not hasProtocol:
            start = stop = pause = next_ = False
        elif status in (None, "waiting"):
            start, stop, pause, next_ = True, False, False, False
        elif status == "running":
            start, stop, pause, next_ = False, True, True, True
        elif status == "paused":
            start, stop, pause, next_ = False, True, True, False
        elif status == "error":
            start, stop, pause, next_ = False, True, False, False
        else:
            start, stop, pause, next_ = False, False, False, False
        self.startBtn.setEnabled(start)
        self.stopBtn.setEnabled(stop)
        self.pauseBtn.setEnabled(pause)
        self.nextBtn.setEnabled(next_)
        self.pauseBtn.setText("Resume" if status == "paused" else "Pause")
