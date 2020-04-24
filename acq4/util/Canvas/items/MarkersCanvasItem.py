# -*- coding: utf-8 -*-
from __future__ import print_function
import weakref
from acq4.util import Qt
from .CanvasItem import CanvasItem
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.graphicsItems.TargetItem
from .itemtypes import registerItemType


class MarkersCanvasItem(CanvasItem):
    """
    Canvas item used for marking multiple locations in 3D.
    
    """
    _typeName = "Markers"
    
    def __init__(self, **kwds):
        kwds.pop('viewRect', None)
        
        item = pg.ItemGroup()
        opts = {'scalable': False, 'rotatable': False, 'movable': False}
        opts.update(kwds)        
        CanvasItem.__init__(self, item, **opts)

        self.params = pg.parametertree.Parameter.create(name='Markers', type='group', addText='Add marker...')
        self.params.addNew = self.addMarker
        self.params.sigTreeStateChanged.connect(self._paramsChanged)

        self._markerCtrl = MarkerItemCtrlWidget(self)
        self.layout.addWidget(self._markerCtrl, self.layout.rowCount(), 0, 1, 2)

    @classmethod
    def checkFile(cls, fh):
        return 0
    
    def addMarker(self, name='marker', position=(0, 0, 0), params=None):
        children = [
            PointParameter(name='Position', value=position)
        ]
        # allow adding extra parameters when adding new markers
        if params is not None:
            children.extend(kwds['params'])
        
        param = pg.parametertree.Parameter.create(name=name, autoIncrementName=True, type='group', renamable=True, removable=True, children=children)
        self.params.addChild(param)

        target = pg.graphicsItems.TargetItem.TargetItem()
        target.setLabel(name)
        target.setLabelAngle(45)
        target.setParentItem(self.graphicsItem())
        target.setPos(position[0], position[1])
        target.param = weakref.ref(param)
        target.sigDragged.connect(self._targetMoved)
        param.target = target
    
    def removeMarker(self, name):
        param = self.params.child(name)
        self.params.removeChild(param)
        param.target.scene().removeItem(target)

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

    def _paramsChanged(self, root, changes):
        for param, change, args in changes:
            if change == 'value' and isinstance(param, PointParameter):
                target = param.parent().target
                with pg.SignalBlock(target.sigDragged, self._targetMoved):
                    target.setPos(*param.value()[:2])
            elif change == 'name' and param in self.params.children():
                param.target.setLabel(param.name())

    def saveState(self, **kwds):
        state = CanvasItem.saveState(self, **kwds)
        state['markers'] = [(p.name(), p['Position']) for p in self.params.children()]
        return state

    def restoreState(self, state):
        markers = state.pop('markers')
        CanvasItem.restoreState(self, state)
        for marker in self.params.children():
            self.removeMarker(marker.name())
        for name, pos in markers:
            self.addMarker(name, pos)


class PointParameterItem(pg.parametertree.ParameterItem):
    def __init__(self, param, depth):
        pg.parametertree.ParameterItem.__init__(self, param, depth)
        self.valueChanged(self.param, self.param.value())

    def valueChanged(self, param, val):
        strs = tuple([pg.siFormat(x, suffix='m') for x in val])
        self.setText(1, '[%s, %s, %s]' % strs)


class PointParameter(pg.parametertree.Parameter):

    itemClass = PointParameterItem

    def __init__(self, **kwds):
        pos = kwds.get('value', (0, 0, 0))
        pg.parametertree.Parameter.__init__(self, expanded=False, children=[
                {'name': 'x', 'type': 'float', 'value': pos[0], 'suffix': 'm', 'siPrefix': True, 'step': 10e-6},
                {'name': 'y', 'type': 'float', 'value': pos[1], 'suffix': 'm', 'siPrefix': True, 'step': 10e-6},
                {'name': 'z', 'type': 'float', 'value': pos[2], 'suffix': 'm', 'siPrefix': True, 'step': 10e-6},
        ], **kwds)
        self._updateChildren()
        self.sigTreeStateChanged.connect(self._treeStateChanged)

    def _updateChildren(self):
        with pg.SignalBlock(self.sigTreeStateChanged, self._treeStateChanged):
            self['x'], self['y'], self['z'] = self.value()

    def _treeStateChanged(self, root, changes):
        # child parameter value changed; update this value to match

        for param, change, args in changes:
            if change != 'value':
                continue
            if param is self:
                self._updateChildren()
            else:
                with pg.SignalBlock(self.sigTreeStateChanged, self._treeStateChanged):
                    self.setValue((self['x'], self['y'], self['z']))

registerItemType(MarkersCanvasItem)


class MarkerItemCtrlWidget(Qt.QWidget):
    def __init__(self, canvasitem):
        Qt.QWidget.__init__(self)
        self.canvasitem = weakref.ref(canvasitem)

        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        
        self.ptree = pg.parametertree.ParameterTree(showHeader=False)
        self.ptree.setParameters(canvasitem.params)
        self.layout.addWidget(self.ptree, 0, 0, 1, 2)

        self.saveJsonBtn = Qt.QPushButton('Save Json')
        self.layout.addWidget(self.saveJsonBtn, 1, 0)
        self.saveJsonBtn.clicked.connect(self.saveJson)
        
        self.copyJsonBtn = Qt.QPushButton('Copy Json')
        self.layout.addWidget(self.copyJsonBtn, 1, 0)
        self.copyJsonBtn.clicked.connect(self.copyJson)

    def saveJson(self):
        filename = Qt.QFileDialog.getSaveFileName(None, "Save markers", path, "JSON files (*.json)")
        if filename == '':
            return
        if not filename.endswith('.json'):
            filename += '.json'

    def copyJson(self):
        pass
    