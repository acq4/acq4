"""ProtocolPanel: Area 4's protocol picker -- lists .py protocol files in the
operator's protocol directory (via ProtocolDirectory) and loads the selected
one as a ProtocolFile."""
from __future__ import annotations

import os

from pyqtgraph.parametertree import ParameterTree

from acq4.experiment.protocol_directory import ProtocolDirectory
from acq4.experiment.protocol_file import ProtocolFile, ProtocolLoadError
from acq4.util import Qt
from acq4.util.codeEditor import invokeCodeEditor

from .sizing import CompactLabel, rowsHigh


class _CompactParamTree(ParameterTree):
    """The loaded protocol's parameters, in a tree that gives way rather than
    insists.

    A ParameterTree's own minimum is QAbstractScrollArea's -- some seventy
    pixels, its guess at the smallest viewport still worth scrolling, and
    nothing to do with what is in the tree. Area 4 is a scrolling viewport over
    this whole panel (see AutopatchWindow._makeArea), so that guess is height
    the panel refuses to give up: squeezing the area past it scrolls the picker
    and Reload off the top of the area instead of shortening the tree. Three
    parameter rows and then scroll within itself is what an operator squeezing
    Area 4 is asking for.

    The preferred height is floored at four rows for the case ParameterTree
    itself has no answer to: its sizeHint is the sum of the rows it holds, which
    is nothing at all until a protocol is loaded, and the window's opening
    division of the right-hand column is seeded from exactly these hints (see
    AutopatchWindow._seedOpeningSplit). A smaller minimum is the point of this
    class; a smaller preference would only open Area 4 as a sliver.
    """

    def minimumSizeHint(self):
        return Qt.QSize(0, rowsHigh(self, 3))

    def sizeHint(self):
        hint = super().sizeHint()
        return Qt.QSize(hint.width(), max(hint.height(), rowsHigh(self, 4)))


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
        """`protocolDir` is the operator's protocol directory -- everything this
        panel lists lives there, including the copies of the bundled examples
        that AutopatchWindow seeds into it (see
        acq4.modules.Autopatch.example_protocols)."""
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
        # While pinned, the one protocol on offer, addressed by path rather than
        # through self.directory (whose stem-keyed discovery lets a same-named
        # file in protocolDir shadow it).
        self._pinned: ProtocolFile | None = None
        self._nameBeforePin: str | None = None
        self._interactionEnabled = True

        self.fileCombo = _RescanningComboBox(onOpen=self.refreshFileList)
        self.reloadBtn = Qt.QPushButton("Reload")
        self.editorBtn = Qt.QPushButton("Open in editor")
        self.editorBtn.setEnabled(False)

        row = Qt.QHBoxLayout()
        row.addWidget(self.fileCombo)
        row.addWidget(self.reloadBtn)
        row.addWidget(self.editorBtn)

        self.paramTree = _CompactParamTree(showHeader=False)
        # A load error is one long line of Python -- a traceback's last line, or
        # an import failure naming a path -- and unwrapped it would decide how
        # wide this panel has to be, which in Area 4 means a horizontal
        # scrollbar under everything else. CompactLabel wraps it without letting
        # the wrapping cost unbounded height in return.
        self.errorLabel = CompactLabel()
        self.bannerLabel = CompactLabel()
        self.bannerLabel.setVisible(False)

        outer = Qt.QVBoxLayout()
        outer.addWidget(self.bannerLabel)
        outer.addLayout(row)
        # The tree is the only thing here that can use more room, and the only
        # thing that can do without it; the picker row and the error line are
        # each one row of controls either way.
        outer.addWidget(self.paramTree, 1)
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
        if self._pinned is None:
            self.directory.scan()
        self._rebuildCombo()

    def forceReloadFileList(self) -> None:
        """Force-reload every discovered protocol, including one that is
        already loaded -- the explicit Reload button's path. A pinned protocol
        is re-read from its own path instead."""
        if self._pinned is not None:
            self._pinned = self._loadedProtocolFile(self._pinned.path)
            self._selectedName = None
        else:
            self.directory.reload_all()
        self._rebuildCombo()

    def _rebuildCombo(self) -> None:
        self._rebuildComboSelecting(self.fileCombo.currentData())

    def _rebuildComboSelecting(self, current: str | None) -> None:
        self.fileCombo.blockSignals(True)
        self.fileCombo.clear()
        if self._pinned is not None:
            label = self._pinned.name if self._pinned.is_loaded else f"{self._pinned.name} (error)"
            self.fileCombo.addItem(label, self._pinned.name)
        if self._pinned is None:
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

    def _currentProtocol(self) -> ProtocolFile:
        if self._pinned is not None:
            return self._pinned
        return self.directory.protocols[self._currentName()]

    @staticmethod
    def _loadedProtocolFile(path: str) -> ProtocolFile:
        protocol = ProtocolFile(path)
        try:
            protocol.load()
        except ProtocolLoadError:
            pass  # surfaced through protocol.load_error, as for a discovered file
        return protocol

    def isPinned(self) -> bool:
        return self._pinned is not None

    def pinProtocol(self, path: str, banner: str) -> None:
        """Offer exactly one protocol, addressed by `path`, and lock the picker
        onto it. Bypasses ProtocolDirectory so a same-named file in protocolDir
        cannot stand in for it."""
        if self._pinned is None:
            self._nameBeforePin = self._currentName()
        self._pinned = self._loadedProtocolFile(path)
        self.bannerLabel.setText(banner)
        self.bannerLabel.setVisible(True)
        self._selectedName = None
        self._rebuildCombo()
        self._applyComboEnabled()

    def unpinProtocol(self) -> None:
        """Back to normal discovery, reselecting what was selected before the
        pin if it still exists."""
        if self._pinned is None:
            return
        self._pinned = None
        self.bannerLabel.setVisible(False)
        self._selectedName = None
        self.directory.scan()
        self._rebuildComboSelecting(self._nameBeforePin)
        self._applyComboEnabled()

    def _applyComboEnabled(self) -> None:
        self.fileCombo.setEnabled(self._interactionEnabled and self._pinned is None)

    def _onSelectionChanged(self, *args) -> None:
        """The selected protocol IS the loaded protocol -- there is no separate
        Load step. This runs for an actual operator selection and for a
        combo repopulate that lands back on the same entry (_rebuildCombo()
        calls this unconditionally after every scan), so sigProtocolLoaded
        only fires when `name` genuinely differs from the previous call --
        see self._selectedName. It never reloads the protocol itself: the
        already-scanned ProtocolFile from self.directory is used as-is, so an
        operator's param edits survive clicking away and back (reloading is
        forceReloadFileList()'s job -- the Reload button). When nothing loadable is
        selected (no entry, or one that failed to load), protocolFile is None
        rather than the previously loaded protocol; AutopatchWindow refuses
        Start on that."""
        name = self._currentName()
        self.editorBtn.setEnabled(name is not None)
        changed = name != self._selectedName
        self._selectedName = name
        if name is None:
            self.protocolFile = None
            self.paramTree.clear()
            self.errorLabel.setText("")
            return
        protocol = self._currentProtocol()
        if protocol.is_loaded:
            self.errorLabel.setText("")
            self.paramTree.setParameters(protocol.param_tree, showTop=False)
            self.protocolFile = protocol
            if changed:
                self.sigProtocolLoaded.emit(protocol)
        else:
            self.protocolFile = None
            self.paramTree.clear()
            self.errorLabel.setText(protocol.load_error or "")

    def setInteractionEnabled(self, enabled: bool) -> None:
        """Gate the protocol picker and Reload -- disabled while a run is in
        flight, so the operator can't select a second protocol out from
        under a still-running Orchestrator (leaving two worker threads
        eligible to drive the same pipette). Open-in-editor is left alone:
        editing the file on disk doesn't touch the live run."""
        self._interactionEnabled = enabled
        self._applyComboEnabled()
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
        protocol = self._currentProtocol()
        invokeCodeEditor(protocol.path, 1)
