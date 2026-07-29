"""ProtocolPanel: Area 4's protocol picker -- lists .py protocol files in a
directory (via ProtocolDirectory) and loads the selected one as a ProtocolFile."""
from __future__ import annotations

import os
import subprocess

from pyqtgraph.parametertree import ParameterTree

from acq4.experiment.protocol_directory import ProtocolDirectory
from acq4.experiment.protocol_file import ProtocolFile
from acq4.util import Qt


class _RescanningComboBox(Qt.QComboBox):
    """A QComboBox that rescans the protocol directory just before its popup
    opens, so a protocol dropped onto disk shows up without an explicit
    Reload click."""

    def __init__(self, onOpen):
        super().__init__()
        self._onOpen = onOpen

    def showPopup(self) -> None:
        self._onOpen()
        super().showPopup()


class ProtocolPanel(Qt.QWidget):
    sigProtocolLoaded = Qt.Signal(object)  # ProtocolFile

    def __init__(self, protocolDir: str):
        super().__init__()
        self.protocolDir = protocolDir
        os.makedirs(self.protocolDir, exist_ok=True)
        self.directory = ProtocolDirectory(self.protocolDir)
        self.protocolFile: ProtocolFile | None = None

        self.fileCombo = _RescanningComboBox(onOpen=self.refreshFileList)
        self.reloadBtn = Qt.QPushButton("Reload")
        self.loadBtn = Qt.QPushButton("Load")
        self.editorBtn = Qt.QPushButton("Open in editor")
        self.editorBtn.setEnabled(False)

        row = Qt.QHBoxLayout()
        row.addWidget(self.fileCombo)
        row.addWidget(self.reloadBtn)
        row.addWidget(self.loadBtn)
        row.addWidget(self.editorBtn)

        self.paramTree = ParameterTree(showHeader=False)
        self.errorLabel = Qt.QLabel()
        self.errorLabel.setWordWrap(True)

        outer = Qt.QVBoxLayout()
        outer.addLayout(row)
        outer.addWidget(self.paramTree)
        outer.addWidget(self.errorLabel)
        self.setLayout(outer)

        self.reloadBtn.clicked.connect(self.refreshFileList)
        self.loadBtn.clicked.connect(self.loadSelected)
        self.editorBtn.clicked.connect(self.openInEditor)
        self.fileCombo.currentIndexChanged.connect(self._onSelectionChanged)

        self.refreshFileList()

    def refreshFileList(self) -> None:
        current = self.fileCombo.currentData()
        self.directory.scan()
        self.fileCombo.blockSignals(True)
        self.fileCombo.clear()
        for name in sorted(self.directory.protocols):
            protocol = self.directory.protocols[name]
            label = name if protocol.is_loaded else f"{name} (error)"
            self.fileCombo.addItem(label, name)
        if current is not None:
            idx = self.fileCombo.findData(current)
            if idx >= 0:
                self.fileCombo.setCurrentIndex(idx)
        self.fileCombo.blockSignals(False)
        self._onSelectionChanged()

    def _currentName(self) -> str | None:
        return self.fileCombo.currentData()

    def _onSelectionChanged(self, *args) -> None:
        name = self._currentName()
        self.editorBtn.setEnabled(name is not None)
        if name is None:
            self.paramTree.clear()
            self.errorLabel.setText("")
            return
        protocol = self.directory.protocols[name]
        if protocol.is_loaded:
            self.errorLabel.setText("")
            self.paramTree.setParameters(protocol.param_tree, showTop=False)
        else:
            self.paramTree.clear()
            self.errorLabel.setText(protocol.load_error or "")

    def loadSelected(self) -> ProtocolFile | None:
        name = self._currentName()
        if name is None:
            return None
        self.directory.reload(name)
        protocol = self.directory.get(name)
        if not protocol.is_loaded:
            self.paramTree.clear()
            self.errorLabel.setText(protocol.load_error or "")
            return None
        self.protocolFile = protocol
        self.errorLabel.setText("")
        self.paramTree.setParameters(protocol.param_tree, showTop=False)
        self.sigProtocolLoaded.emit(protocol)
        return protocol

    def openInEditor(self) -> None:
        name = self._currentName()
        if name is None:
            return
        protocol = self.directory.protocols[name]
        editor = os.environ.get("EDITOR") or "xdg-open"
        subprocess.Popen([editor, protocol.path])
