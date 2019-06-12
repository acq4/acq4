from PyQt4 import QtGui, QtCore
from acq4.pyqtgraph.graphicsItems.TargetItem import TargetItem
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
import numpy as np

class Photostimulation():
    """A data modelling class that represents a single focal photostimulation."""

    def __init__(self, info, id):
        #self._info = info
        self.id = id
        self.info = info
        self.info['id'] = id

    def __repr__(self):
        return self.info.__repr__()
     





class StimulationPoint(QtCore.QObject):

    sigStimPointChanged = QtCore.Signal(object)
    sigTargetDragged = QtCore.Signal(object)
    sigZAxisStimRequested = QtCore.Signal(object)

    def __init__(self, name, itr, pos, z):
        QtCore.QObject.__init__(self)
        self.name = "%s %i" % (name, itr)
        self.id = itr
        self.z = z
        self.graphicsItem = PhotostimTarget(pos, label=itr)
        self.depthGraphicsItem = PhotostimTarget((0,z), label=itr, contextMenuEnabled=False, movable=False)
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=False, renamable=True)

        self.params.sigValueChanged.connect(self.changed)
        self.graphicsItem.sigDragged.connect(self.targetDragged)
        self.graphicsItem.sigCellBtnToggled.connect(self.cellBtnToggled)
        self.graphicsItem.sigZaxisStimRequested.connect(self.zAxisStimRequested)

#        self.positionHistory = []
        self.stimulations = []

        self.onCell = True


    def changed(self, param):
        self.sigStimPointChanged.emit(self)

    def targetDragged(self):
#        self.updateHistory()
        self.sigTargetDragged.emit(self)

    def setDepth(self, z):
        self.z = z
        self.depthGraphicsItem.setPos(0, z)
#        self.updateHistory()
        self.changed(z)

    def getPos(self):
        ## return position in global coordinates
        return (self.graphicsItem.pos().x(), self.graphicsItem.pos().y(), self.z)

#    def updateHistory(self, timestamp=None, pos=None):
#        if timestamp is None:
#            timestamp = time.time()
#        if pos is None:
#            pos = self.getPos()
#        self.positionHistory.append((timestamp, pos))

    def addStimulation(self, data, id):
        self.stimulations.append({id:data})

    def updatePosition(self, pos):
        self.setDepth(pos[2])
        self.graphicsItem.setPos(pos[0], pos[1])

    def cellBtnToggled(self, b):
        if b:
            self.onCell = True
        else:
            self.onCell = False

    def saveState(self):
        d = {}
        d['id'] = self.id
        d['position'] = self.getPos()
        d['name'] = self.name
        d['onCell'] = self.onCell

        return d

    def zAxisStimRequested(self):
        self.sigZAxisStimRequested.emit(self)



class PhotostimTarget(TargetItem):
    ## inherits from TargetItem, GraphicsObject, GraphicsItem, QGraphicsObject

    sigCellBtnToggled = QtCore.Signal(object)
    sigZaxisStimRequested = QtCore.Signal()

    def __init__(self, pos, label, contextMenuEnabled=True, **args):
        #self.enabledPen = pg.mkPen((0, 255, 255))
        #self.disabledPen = pg.mkPen((150,150,150))
        #self.enabledBrush = pg.mkBrush((0,0,255,100))
        #self.disabledBrush = pg.mkBrush((0,0,255,0))
        TargetItem.__init__(self, **args)

        self.setLabel(str(label))
        self.setPos(pg.Point(pos))
        #print("PhotostimTarget:", pos)

        #### Set up context menu
        self.menu = QtGui.QMenu()
        self.menu.setTitle("StimulationPoint")

        self._contextMenuAllowed = contextMenuEnabled
        if self._contextMenuAllowed:
            ## set up on-cell/off-cell buttons
            act = QtGui.QWidgetAction(self)
            w = QtGui.QWidget()
            l = QtGui.QVBoxLayout()
            l.setContentsMargins(3,3,3,3)
            l.setSpacing(3)
            w.setLayout(l)
            self.onCellBtn = QtGui.QCheckBox("On-cell")
            self.onCellBtn.setChecked(True)
            l.addWidget(self.onCellBtn)
            #self.offCellBtn = QtGui.QRadioButton("Off-cell")
            #l.addWidget(self.offCellBtn)
            act.setDefaultWidget(w)
            self.onCellBtn.toggled.connect(self.cellBtnToggled)
            self.menu.addAction(act)

            act2 = QtGui.QAction("Run z-axis supplemental stimulation", self.menu)
            self.menu.addAction(act2)
            act2.triggered.connect(self.suppStimRequested)

    def contextMenuEnabled(self):
        return self._contextMenuAllowed

    def setEnabledPen(self, b):
        if b:
            self.pen = pg.mkPen(color=self.pen.color(), width=3)
            #self.brush = self.enabledBrush
        else:
            self.pen = pg.mkPen(color=self.pen.color(), width=1)
            #self.brush = self.disabledBrush

        self._picture = None
        self.update()

    def setRelativeDepth(self, depth):
        # adjust the apparent depth of the target
        dist = depth * 255 / 50e-6
        color = (np.clip(dist+256, 0, 255), np.clip(256-dist, 0, 255), 0, 150)
        self.pen = pg.mkPen(color)
        self._picture = None
        self.update()

    def getMenu(self):
        return self.menu

    def raiseContextMenu(self, ev):
        if not self.contextMenuEnabled():
            return
        menu = self.getMenu()
        menu = self.scene().addParentContextMenus(self, menu, ev)
        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton and self.contextMenuEnabled():
            self.raiseContextMenu(ev)
            ev.accept()

    def cellBtnToggled(self, b):
        QtCore.QTimer.singleShot(300, self.menu.hide)
        #print("CellBtnToggled", b)
        self.sigCellBtnToggled.emit(b)

    def suppStimRequested(self):
        self.sigZaxisStimRequested.emit()
