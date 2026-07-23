"""StatusPanel: Area 3's global controls (Start/Stop/Pause/Next) and the big
Running/Waiting/Paused/Error status indicator bound to an Orchestrator."""
from __future__ import annotations

from acq4.util import Qt


class StatusPanel(Qt.QWidget):
    def __init__(self):
        super().__init__()
        self._orchestrator = None
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

    def bindOrchestrator(self, orchestrator, onStart=None) -> None:
        """Bind Start/Stop/Pause/Next to `orchestrator`.

        `onStart`, if given, is called on the GUI thread when Start is clicked,
        before `orchestrator.start()` -- the seam a caller uses to snapshot any
        GUI-thread-only state (e.g. the selected pipette) before the
        orchestrator's worker thread begins running.
        """
        if self._orchestrator is not None:
            self.unbindOrchestrator()

        self._orchestrator = orchestrator
        self._onStart = onStart
        # A freshly bound orchestrator hasn't reported a status yet -- treat it
        # the same as "waiting" so Start is enabled and Stop/Pause/Next are not.
        self._currentStatus = None
        self.startBtn.clicked.connect(self._onStartClicked)
        self.stopBtn.clicked.connect(orchestrator.stop)
        self.pauseBtn.clicked.connect(self._onPauseClicked)
        self.nextBtn.clicked.connect(orchestrator.requestNextCell)
        orchestrator.sigStatus.connect(self._onStatus)
        orchestrator.sigCurrentAction.connect(self._onCurrentAction)
        self._updateButtons()

    def unbindOrchestrator(self) -> None:
        """Disconnect everything bindOrchestrator() connected to the currently
        bound orchestrator, and drop the reference to it.

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
        Qt.disconnect(self._orchestrator.sigCurrentAction, self._onCurrentAction)
        self._orchestrator = None
        self._onStart = None
        self._currentStatus = None
        self._updateButtons()

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

    def _onCurrentAction(self, cell, action) -> None:
        if action is None:
            self.currentActionLabel.setText("")
            return
        self.currentActionLabel.setText(f"{action.name} — {cell!r}")

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
