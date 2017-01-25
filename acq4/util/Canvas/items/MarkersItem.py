# -*- coding: utf-8 -*-
import weakref
from PyQt4 import QtCore, QtGui
from .CanvasItem import CanvasItem
import acq4.pyqtgraph as pg


class MarkersItem(CanvasItem):
    """
    Canvas item used for marking multiple locations in 3D.
    
    """
    
    def __init__(self, **kwds):
        item = pg.ItemGroup()
        opts = {'name': 'markers', 'scalable': False, 'rotatable': False, 'movable': False}
        opts.update(kwds)
        
        CanvasItem.__init__(self, item, **opts)

        self.params = pg.parametertree.Parameter.create(name='Markers', type='group', addText='Add marker...')
        self.params.addNew = self.addMarker
        
        self._ctrl = MarkerItemCtrlWidget(self)
        self.layout.addWidget(self._ctrl, self.layout.rowCount(), 0, 1, 2)
    
    @classmethod
    def checkFile(cls, fh):
        return 0
    
    def addMarker(self, name='marker'):
        param = pg.parametertree.Parameter.create(name=name, autoIncrementName=True, type='group', renamable=True, removable=True, children=[
            {'name': 'Position', 'type': 'group', 'children': [
                {'name': 'x', 'type': 'float', 'value': 0, 'suffix': 'm', 'siPrefix': True},
                {'name': 'y', 'type': 'float', 'value': 0, 'suffix': 'm', 'siPrefix': True},
                {'name': 'z', 'type': 'float', 'value': 0, 'suffix': 'm', 'siPrefix': True},
            ]},
        ])
        self.params.addChild(param)
    
    
class MarkerItemCtrlWidget(QtGui.QSplitter):
    def __init__(self, canvasitem):
        QtGui.QSplitter.__init__(self)
        self.canvasitem = weakref.ref(canvasitem)

        self.ptree = pg.parametertree.ParameterTree(showHeader=False)
        self.ptree.setParameters(canvasitem.params)
            
        self.addWidget(self.ptree)

        self.ctrlWidget = QtGui.QWidget(self)
        self.ctrlLayout = QtGui.QGridLayout()
        self.ctrlWidget.setLayout(self.ctrlLayout)

        self.addWidget(self.ctrlWidget)

        btns = [
            # ('setCellPosition', "Set selected cell position"),
            ('saveJson', 'Save JSON'),
        ]
        self.btns = {}
        for name, text in btns:
            btn = QtGui.QPushButton(text)
            self.btns[name] = btn
            self.ctrlLayout.addWidget(btn, self.ctrlLayout.rowCount(), 0)
            slot = getattr(self, name)
            btn.clicked.connect(slot)

    def setMarkerPosition(self):
        self.btns['setCellPosition'].setText("Click on new cell position")
        # Evaluate items under click, ignore anything that is transparent, and raise an exception if the top item is partially transparent.
        # what if the top item has a composition mode that renders it invisible? 
        # Maybe we just need a global focus similar to the camera module?
            # just show one line for the most recently-updated image depth?
            # One line per image?

    def saveJson(self):
        filename = QtGui.QFileDialog.getSaveFileName(None, "Save markers", path, "JSON files (*.json)")
        if filename == '':
            return
        if not filename.endswith('.json'):
            filename += '.json'

        
    