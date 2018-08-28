from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from PyQt4 import QtGui, QtCore
import moduleTemplate
import pyqtgraph as pg
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.graphicsItems.TargetItem import TargetItem

class PrairiePhotostimulator(Device, OptomechDevice):

    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)


    def moduleGui(self, mod):
        return PrairiePhotostimModGui(self, mod)


class PrairiePhotostimModGui(QtGui.QWidget):

    def __init__(self, dev, parent):
        QtGui.QWidget.__init__(self, parent)

        self.dev = dev
        self.ui = moduleTemplate.Ui_Form()
        self.ui.setupUi(self)

        self.spiralParams = pTypes.GroupParameter(name="SpiralParameters", type='group', removable=False, renamable=False, children=[
            dict(name='spiral revolutions', type='float', value='5.0', bounds=[0, None], step=1),
            dict(name='laser power', type='int', value=0, bounds=[0, None], step=1),
            dict(name='duration', type='float', value=0.01, bounds=[0, None], suffix='s', siPrefix=True, step=1e-3),
            dict(name='size', type='float', value=10e-6, bounds=[0, None], suffix='m', siPrefix=True, step=1e-6)
            ])

        self.ui.stimulusParamTree.addParameters(self.spiralParams)
        self.stimPoints = []
        self.counter = 0


    def addStimPoint(self, pos):
        name, itr = self.getNextName()
        sp = StimulationPoint(name, itr, pos)
        self.ui.pointsParamTree.addParameters(sp.params)
        self.stimPoints.append(sp)
        return sp.graphicsItem

    def getNextName(self):
        self.counter += 1
        return ("Point", self.counter)




class StimulationPoint():

    def __init__(self, name, itr, pos):

        self.name = "%s %i" % (name, itr)
        self.graphicsItem = PhotostimTarget(pos, label=itr)
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True)

        self.params.sigValueChanged.connect(self.valueChanged)

    def valueChanged(self, b):
        self.graphicsItem.setEnabledPen(b)


class PhotostimTarget(TargetItem):

    def __init__(self, pos, label):
        TargetItem.__init__(self)

        self.setLabel(str(label))
        self.setPos(pg.Point(pos))

        self.enabledPen = pg.mkPen((100, 255, 0))
        self.disabledPen = pg.mkPen((150,150,150))

        #self.translate(-size/2., -size/2.)

    #def _addHandles(self):
        #self.addRotateHandle([1.0, 0.5], [0.5, 0.5])
        #self.addScaleHandle([0.5*2.**-0.5 + 0.5, 0.5*2.**-0.5 + 0.5], [0.5, 0.5])
        #print("Calling new addHandles class")

    def setEnabledPen(self, b):
        if b:
            self.setPen(self.enabledPen)
        else:
            self.setPen(self.disabledPen)
