"""Autopatch module: the operator-facing run window for the experiment
orchestration engine (acq4/experiment/). See autopatch-orchestration-design.md."""
from __future__ import annotations

from acq4.modules.Module import Module
from acq4.util import Qt


class AutopatchWindow(Qt.QWidget):
    """The Autopatch run window: five labeled areas per the design doc.

    This task only builds empty placeholder group boxes; later tasks add each
    area's real content (protocol selection, status/controls, cell list).
    """

    def __init__(self, module: "Autopatch | None" = None):
        super().__init__()
        self.module = module
        self.setWindowTitle("Autopatch")

        self.area1Box = Qt.QGroupBox("Area 1 — Slice && region")
        self.area2Box = Qt.QGroupBox("Area 2 — Cell finding")
        self.area3Box = Qt.QGroupBox("Area 3 — Status && actions")
        self.area4Box = Qt.QGroupBox("Area 4 — Protocol && params")
        self.area5Box = Qt.QGroupBox("Area 5 — Current cell")

        for box in (self.area1Box, self.area2Box, self.area3Box, self.area4Box, self.area5Box):
            box.setLayout(Qt.QVBoxLayout())

        topRow = Qt.QHBoxLayout()
        topRow.addWidget(self.area1Box)
        topRow.addWidget(self.area2Box)

        bottomRow = Qt.QHBoxLayout()
        bottomRow.addWidget(self.area3Box)
        bottomRow.addWidget(self.area4Box)
        bottomRow.addWidget(self.area5Box)

        outer = Qt.QVBoxLayout()
        outer.addLayout(topRow)
        outer.addLayout(bottomRow)
        self.setLayout(outer)


class Autopatch(Module):
    moduleDisplayName = "Autopatch"
    moduleCategory = "Utilities"
    _instance = None

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        if Autopatch._instance is not None:
            Autopatch._instance.ui.raise_()
            Autopatch._instance.ui.activateWindow()
            Qt.QTimer.singleShot(0, self.quit)
            return
        Autopatch._instance = self
        self.ui = AutopatchWindow(self)
        manager.declareInterface(name, ["autopatchModule"], self)
        self.ui.show()

    def window(self):
        return self.ui

    def quit(self, fromUi=False):
        if Autopatch._instance is self:
            Autopatch._instance = None
        if hasattr(self, "ui") and not fromUi:
            self.ui.close()
        super().quit()
