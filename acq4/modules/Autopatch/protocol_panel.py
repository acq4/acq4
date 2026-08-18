"""ProtocolPanel: Area 4's protocol picker -- lists .py protocol files in a
directory (via ProtocolDirectory) and loads the selected one as a ProtocolFile."""
from __future__ import annotations

import os

from pyqtgraph.parametertree import ParameterTree

from acq4.experiment.protocol_directory import ProtocolDirectory
from acq4.experiment.protocol_file import ProtocolFile
from acq4.util import Qt
from acq4.util.codeEditor import invokeCodeEditor


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
        # Name of the protocol _onSelectionChanged last processed, so a rescan
        # that repopulates the combo and reselects the same entry (see
        # _rebuildCombo() below, and _RescanningComboBox.showPopup()) can tell
        # "still the same selection" from "the operator picked something
        # else" and only emit sigProtocolLoaded for a genuine change.
        self._selectedName: str | None = None

        self.fileCombo = _RescanningComboBox(onOpen=self.refreshFileList)
        self.reloadBtn = Qt.QPushButton("Reload")
        self.editorBtn = Qt.QPushButton("Open in editor")
        self.editorBtn.setEnabled(False)

        row = Qt.QHBoxLayout()
        row.addWidget(self.fileCombo)
        row.addWidget(self.reloadBtn)
        row.addWidget(self.editorBtn)

        self.paramTree = ParameterTree(showHeader=False)
        self.errorLabel = Qt.QLabel()
        self.errorLabel.setWordWrap(True)

        outer = Qt.QVBoxLayout()
        outer.addLayout(row)
        outer.addWidget(self.paramTree)
        outer.addWidget(self.errorLabel)
        self.setLayout(outer)

        self.reloadBtn.clicked.connect(self.forceReloadFileList)
        self.editorBtn.clicked.connect(self.openInEditor)
        self.fileCombo.currentIndexChanged.connect(self._onSelectionChanged)

        self.refreshFileList()

    def refreshFileList(self) -> None:
        """Discovery-only rescan: picks up new/removed files and retries any
        that previously failed to load, but never re-imports an
        already-loaded protocol -- see `_RescanningComboBox.showPopup()`,
        which calls this just before the popup opens. Use `forceReloadFileList()`
        (the Reload button) to re-import everything, including the one that's
        currently loaded."""
        self.directory.scan()
        self._rebuildCombo()

    def forceReloadFileList(self) -> None:
        """Force-reload every discovered protocol, including one that is
        already loaded -- the explicit Reload button's path."""
        self.directory.reload_all()
        self._rebuildCombo()

    def _rebuildCombo(self) -> None:
        current = self.fileCombo.currentData()
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
        """The selected protocol IS the loaded protocol -- there is no separate
        Load step. This runs for an actual operator selection and for a
        combo repopulate that lands back on the same entry (_rebuildCombo()
        calls this unconditionally after every scan), so sigProtocolLoaded
        only fires when `name` genuinely differs from the previous call --
        see self._selectedName. It never reloads the protocol itself: the
        already-scanned ProtocolFile from self.directory is used as-is, so an
        operator's param edits survive clicking away and back (reloading is
        forceReloadFileList()'s job -- the Reload button)."""
        name = self._currentName()
        self.editorBtn.setEnabled(name is not None)
        changed = name != self._selectedName
        self._selectedName = name
        if name is None:
            self.paramTree.clear()
            self.errorLabel.setText("")
            return
        protocol = self.directory.protocols[name]
        if protocol.is_loaded:
            self.errorLabel.setText("")
            self.paramTree.setParameters(protocol.param_tree, showTop=False)
            self.protocolFile = protocol
            if changed:
                self.sigProtocolLoaded.emit(protocol)
        else:
            self.paramTree.clear()
            self.errorLabel.setText(protocol.load_error or "")

    def setInteractionEnabled(self, enabled: bool) -> None:
        """Gate the protocol picker and Reload -- disabled while a run is in
        flight, so the operator can't select a second protocol out from
        under a still-running Orchestrator (leaving two worker threads
        eligible to drive the same pipette). Open-in-editor is left alone:
        editing the file on disk doesn't touch the live run."""
        self.fileCombo.setEnabled(enabled)
        self.reloadBtn.setEnabled(enabled)

    def setInteractionLocked(self, locked: bool) -> None:
        """The inverse of setInteractionEnabled(), so this can be connected
        directly to StatusPanel.sigInteractionLocked (a bound-method
        connection, not a lambda closing over the window -- see
        AutopatchWindow.__init__ for why that distinction matters)."""
        self.setInteractionEnabled(not locked)

    def openInEditor(self) -> None:
        name = self._currentName()
        if name is None:
            return
        protocol = self.directory.protocols[name]
        invokeCodeEditor(protocol.path, 1)
