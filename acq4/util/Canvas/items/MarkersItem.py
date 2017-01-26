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
    
    def addMarker(self, name='marker', position=(0, 0, 0), params=None):
        children = [
            {'name': 'Position', 'type': 'group', 'children': [
                {'name': 'x', 'type': 'float', 'value': position[0], 'suffix': 'm', 'siPrefix': True},
                {'name': 'y', 'type': 'float', 'value': position[1], 'suffix': 'm', 'siPrefix': True},
                {'name': 'z', 'type': 'float', 'value': position[2], 'suffix': 'm', 'siPrefix': True},
            ]},
        ]
        # allow adding extra parameters when adding new markers
        if params is not None:
            children.extend(kwds['params'])
        
        param = pg.parametertree.Parameter.create(name=name, autoIncrementName=True, type='group', renamable=True, removable=True, children=children)
        self.params.addChild(param)

        param.target = pg.graphicsItems.TargetItem.TargetItem()
        param.target.setLabel(name)
        param.target.setParentItem(self.graphicsItem())
        param.target.setPos(position[0], position[1])
        param.target.param = weakref.ref(param)
        param.target.sigDragged.connect(self._targetMoved)
    
    def setMarkerPosition(self):
        self.btns['setCellPosition'].setText("Click on new cell position")
        # Evaluate items under click, ignore anything that is transparent, and raise an exception if the top item is partially transparent.
        # what if the top item has a composition mode that renders it invisible? 
        # Maybe we just need a global focus similar to the camera module?
            # just show one line for the most recently-updated image depth?
            # One line per image?

    def _targetMoved(self, target):
        pos = target.pos()
        param = target.param()
        param['Position', 'x'] = pos.x()
        param['Position', 'y'] = pos.y()

    
class MarkerItemCtrlWidget(QtGui.QWidget):
    def __init__(self, canvasitem):
        QtGui.QWidget.__init__(self)
        self.canvasitem = weakref.ref(canvasitem)

        self.layout = QtGui.QGridLayout()
        
        self.ptree = pg.parametertree.ParameterTree(showHeader=False)
        self.ptree.setParameters(canvasitem.params)
        self.layout.addWidget(self.ptree, 0, 0, 1, 2)

        self.saveJsonBtn = QtGui.QPushButton('Save Json')
        self.layout.addWidget(self.saveJsonBtn, 1, 0)
        self.saveJsonBtn.clicked.connect(self.saveJson)
        
        self.copyJsonBtn = QtGui.QPushButton('Copy Json')
        self.layout.addWidget(self.copyJsonBtn, 1, 0)
        self.copyJsonBtn.clicked.connect(self.copyJson)

    def saveJson(self):
        filename = QtGui.QFileDialog.getSaveFileName(None, "Save markers", path, "JSON files (*.json)")
        if filename == '':
            return
        if not filename.endswith('.json'):
            filename += '.json'

    def copyJson(self):
        pass
    