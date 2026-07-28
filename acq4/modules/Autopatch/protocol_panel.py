"""ProtocolPanel: Area 4's protocol picker — lists *.json protocol files in a
directory and loads the selected one via Protocol.load_json."""
from __future__ import annotations

import os

from pyqtgraph.parametertree import Parameter, ParameterTree

from acq4.experiment.protocol import Protocol
from acq4.util import Qt


class ProtocolPanel(Qt.QWidget):
    sigProtocolLoaded = Qt.Signal(object)  # Protocol

    def __init__(self, protocolDir: str):
        super().__init__()
        self.protocolDir = protocolDir
        os.makedirs(self.protocolDir, exist_ok=True)
        self.protocol: Protocol | None = None

        self.fileCombo = Qt.QComboBox()
        self.reloadBtn = Qt.QPushButton("Refresh")
        self.loadBtn = Qt.QPushButton("Load")

        row = Qt.QHBoxLayout()
        row.addWidget(self.fileCombo)
        row.addWidget(self.reloadBtn)
        row.addWidget(self.loadBtn)

        self.paramTree = ParameterTree(showHeader=False)
        self.paramsRoot = None

        outer = Qt.QVBoxLayout()
        outer.addLayout(row)
        outer.addWidget(self.paramTree)
        self.setLayout(outer)

        self.reloadBtn.clicked.connect(self.refreshFileList)
        self.loadBtn.clicked.connect(self.loadSelected)

        self.refreshFileList()

    def refreshFileList(self) -> None:
        current = self.fileCombo.currentText()
        self.fileCombo.clear()
        names = sorted(f for f in os.listdir(self.protocolDir) if f.endswith(".json"))
        self.fileCombo.addItems(names)
        if current in names:
            self.fileCombo.setCurrentText(current)

    def loadSelected(self) -> Protocol:
        name = self.fileCombo.currentText()
        path = os.path.join(self.protocolDir, name)
        self.protocol = Protocol.load_json(path)
        self._rebuildParamTree()
        self.sigProtocolLoaded.emit(self.protocol)
        return self.protocol

    def _rebuildParamTree(self) -> None:
        children = []
        for entry in self.protocol.publicParams:
            action = self.protocol.nodes[entry["node"]]
            srcParam = action.params.child(entry["param"])
            children.append(
                dict(
                    name=entry["public"],
                    type=srcParam.type(),
                    value=srcParam.value(),
                )
            )
        root = Parameter.create(name="params", type="group", children=children)
        for entry in self.protocol.publicParams:
            action = self.protocol.nodes[entry["node"]]
            mirror = root.child(entry["public"])
            mirror.sigValueChanged.connect(
                lambda param, val, node=entry["node"], pname=entry["param"]: (
                    self.protocol.nodes[node].params.child(pname).setValue(val)
                )
            )
        self.paramsRoot = root
        self.paramTree.setParameters(root, showTop=False)
