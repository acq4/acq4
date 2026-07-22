"""StatusPanel: Area 3's global controls (Start/Stop/Pause/Next) and the big
Running/Waiting/Paused/Error status indicator bound to an Orchestrator."""
from __future__ import annotations

from acq4.util import Qt


class StatusPanel(Qt.QWidget):
    def __init__(self):
        super().__init__()
        self._orchestrator = None

        self.startBtn = Qt.QPushButton("Start")
        self.stopBtn = Qt.QPushButton("Stop")
        self.pauseBtn = Qt.QPushButton("Pause")
        self.nextBtn = Qt.QPushButton("Next cell")

        self.statusLabel = Qt.QLabel("idle")
        self.statusLabel.setStyleSheet("font-size: 20pt; font-weight: bold;")
        self.currentActionLabel = Qt.QLabel("")
        self.instructionLabel = Qt.QLabel("")
        self.instructionLabel.setStyleSheet("color: red; font-weight: bold;")
        self.instructionLabel.setVisible(False)

        btnRow = Qt.QHBoxLayout()
        for b in (self.startBtn, self.stopBtn, self.pauseBtn, self.nextBtn):
            btnRow.addWidget(b)

        layout = Qt.QVBoxLayout()
        layout.addLayout(btnRow)
        layout.addWidget(self.statusLabel)
        layout.addWidget(self.currentActionLabel)
        layout.addWidget(self.instructionLabel)
        self.setLayout(layout)

    def bindOrchestrator(self, orchestrator) -> None:
        if self._orchestrator is not None:
            Qt.disconnect(self.startBtn.clicked, self._orchestrator.start)
            Qt.disconnect(self.stopBtn.clicked, self._orchestrator.stop)
            Qt.disconnect(self.pauseBtn.clicked, self._orchestrator.pause)
            Qt.disconnect(self.nextBtn.clicked, self._orchestrator.requestNextCell)
            Qt.disconnect(self._orchestrator.sigStatus, self._onStatus)
            Qt.disconnect(self._orchestrator.sigCurrentAction, self._onCurrentAction)

        self._orchestrator = orchestrator
        self.startBtn.clicked.connect(orchestrator.start)
        self.stopBtn.clicked.connect(orchestrator.stop)
        self.pauseBtn.clicked.connect(orchestrator.pause)
        self.nextBtn.clicked.connect(orchestrator.requestNextCell)
        orchestrator.sigStatus.connect(self._onStatus)
        orchestrator.sigCurrentAction.connect(self._onCurrentAction)

    def _onStatus(self, status: str) -> None:
        self.statusLabel.setText(status)
        self.instructionLabel.setVisible(status == "error")

    def _onCurrentAction(self, cell, action) -> None:
        if action is None:
            self.currentActionLabel.setText("")
            return
        self.currentActionLabel.setText(f"{action.name} — {cell!r}")
