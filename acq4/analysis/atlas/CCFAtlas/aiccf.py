from PyQt4 import QtCore, QtGui
import numpy as np
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.parametertree
import acq4.util.DataManager as DataManager
from .. import Atlas


class CCFAtlas(Atlas.Atlas):
    """MosaicEditor atlas based on Allen Institute Common Coordinate Framework

    * Map slice images to virtual slice of the CCF
    * Layer annotations
    * Multiple 3D cell positions
    * Map cell positions to CCF or to normalized layer coordinates
    """
    def __init__(self):
        Atlas.Atlas.__init__(self)

        self.params = pg.parametertree.Parameter.create(name='Cells', type='group', addText='Add cell...')
        self.params.addNew = self.addNewCell

        self._ctrlWidget = None

    def ctrlWidget(self, host):
        if self._ctrlWidget is None:
            self._ctrlWidget = AICCFCtrlWidget(self, host)
        return self._ctrlWidget

    def addNewCell(self, name='Cell'):
        param = pg.parametertree.Parameter.create(name=name, autoIncrementName=True, type='group', renamable=True, removable=True, children=[
            {'name': 'Position', 'type': 'group', 'children': [
                {'name': 'x', 'type': 'float', 'value': 0, 'suffix': 'm', 'siPrefix': True},
                {'name': 'y', 'type': 'float', 'value': 0, 'suffix': 'm', 'siPrefix': True},
                {'name': 'z', 'type': 'float', 'value': 0, 'suffix': 'm', 'siPrefix': True},
            ]},
            {'name': 'Pipette', 'type': 'str'},
        ])
        self.params.addChild(param)


class AICCFCtrlWidget(QtGui.QSplitter):
    def __init__(self, atlas, host):
        QtGui.QSplitter.__init__(self)
        self.atlas = atlas
        self.host = host

        self.ptree = pg.parametertree.ParameterTree()
        self.ptree.setParameters(atlas.params)
            
        self.addWidget(self.ptree)

        self.ctrlWidget = QtGui.QWidget(self)
        self.ctrlLayout = QtGui.QGridLayout()
        self.ctrlWidget.setLayout(self.ctrlLayout)

        self.addWidget(self.ctrlWidget)

        btns = [
            ('addFromMultipatch', "Add cells from multipatch log"),
            # ('setCellPosition', "Set selected cell position"),
            ('saveJson', 'Save JSON'),
        }
        self.btns = {}
        for name, text in btns:
            btn = QtGui.QPushButton(text)
            self.btns[name] = btn
            self.ctrlLayout.addWidget(btn, self.ctrlLayout.rowCount(), 0)
            slot = getattr(self, name)
            btn.clicked.connect(slot)

    def addFromMultiPatch(self):
        """Add new cells from the current state of the selected multipatch log.
        """

        raise Exception("Please select a loaded multipatch log in the canvas item list.")


    def setCellPosition(self):
        self.btns['setCellPosition'].setText("Click on new cell position")
        # Evaluate items under click, ignore anything that is transparent, and raise an exception if the top item is partially transparent.
        # what if the top item has a composition mode that renders it invisible? 
        # Maybe we just need a global focus similar to the camera module?
            # just show one line for the most recently-updated image depth?
            # One line per image?

