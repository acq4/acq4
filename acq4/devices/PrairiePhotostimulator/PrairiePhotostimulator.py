from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from PyQt4 import QtGui, QtCore
import moduleTemplate
import pyqtgraph as pg
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.graphicsItems.TargetItem import TargetItem
import xml.etree.ElementTree as et
#from acq4.util.PrairieView import PrairieView
import os
from collections import OrderedDict
import numpy as np


baseDicts = {
    'PVMarkPointSeriesElements': OrderedDict([
            ('Iterations', '1'),
            ('IterationDelay', '0')]),
    'PVMarkPointElement': OrderedDict([
            ('Repetitions', '1'),
            ('UncagingLaser', 'Fidelity'),
            ('UncagingLaserPower', '0'),
            ('TriggerFrequency', 'EveryPoint'),
            ('TriggerSelection', 'TrigIn'),
            ('TriggerCount', '1'),
            ('AsyncSyncFrequency', 'EveryPoint'),
            ('VoltageOutputCategoryName', 'None'),
            ('VoltageRecCategoryName','None'),
            ('parameterSet', 'CurrentSettings')]),
    'PVGalvoPointElement':OrderedDict([
            ('InitialDelay', "0.12"),
            ('InterPointDelay', '40'),
            ('Duration','10'),
            ('SpiralRevolutions','5'),
            ('AllPointsAtOnce', 'False'),
            ('Points','Group 1')
            #'Indices':[] ## need to include this when we know how many points there are
            ])}



class PrairiePhotostimulator(Device, OptomechDevice):

    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)

        if config.get('mock', False):
            from acq4.util.MockPrairieView import MockPrairieView
            self.pv = MockPrairieView()
        else:
            ip = config.get('ipaddress', None)
            from acq4.util.PrairieView import PrairieView
            self.pv = PrairieView(ip)

        self._scopeDev = deviceManager.getDevice(config['scopeDevice'])

    def scopeDevice(self):
        return self._scopeDev

    def moduleGui(self, mod):
        return PrairiePhotostimModGui(self, mod)



    def mapToPrairie(self, pos, frame):
        """Map *pos* from global coordinates to frame coordinates, then map frame coordinates to between 0 and 1. """
        #frame = man.getModule('PrairieViewStimulator').window().interface.lastFrame ## get the last frame from PrairieImagerDevice
        ## map pos to frame coordinates, p will be in pixels

        p = pg.Point(frame.globalTransform().inverted()[0].map(pos))
        
        ## map from pixels to percent of image
        xPixels = frame.info()['PrairieMetaInfo']['Environment']['PixelsPerLine']
        yPixels = frame.info()['PrairieMetaInfo']['Environment']['LinesPerFrame']

        x = p.x()/float(xPixels)
        y = p.y()/float(yPixels)

        return (x, y)

    def spiralSizeToPrairie(self, size, frame):
        xPixels = frame.info()['PrairieMetaInfo']['Environment']['PixelsPerLine']
        pixelLength = frame.info()['PrairieMetaInfo']['Environment']['XAxis_umPerPixel']

        x=float(size*1000000)/float(xPixels)/pixelLength
        return x
    

    def runStimulation(self, params):
        self.pv.markPoints(params['pos'], params['laserPower'], params['duration'], params['spiralSize'], params['spiralRevolutions'])



class PrairiePhotostimModGui(QtGui.QWidget):

    def __init__(self, dev, parent):
        QtGui.QWidget.__init__(self, parent)

        self.dev = dev
        self.ui = moduleTemplate.Ui_Form()
        self.ui.setupUi(self)

        self.spiralParams = pTypes.GroupParameter(name="SpiralParameters", type='group', removable=False, renamable=False, children=[
            dict(name='spiral revolutions', type='float', value='5.0', bounds=[0, None], step=1),
            dict(name='laser power', type='int', value=0, bounds=[0, 100], step=1),
            dict(name='duration', type='float', value=0.01, bounds=[0, None], suffix='s', siPrefix=True, step=1e-3),
            dict(name='size', type='float', value=10e-6, bounds=[0, None], suffix='m', siPrefix=True, step=1e-6)
            ])

        self.ui.stimulusParamTree.addParameters(self.spiralParams)
        self.stimPoints = []
        self.counter = 0
        #self.ui.iterationsSpin.setValue(1)

        self.parent().prairieImagerDevice.sigNewFrame.connect(self.newFrame)
        self.dev.scopeDevice().sigGlobalTransformChanged.connect(self.updatePoints)


    def addStimPoint(self, pos):
        name, itr = self.getNextName()
        z = self.dev.scopeDevice().getFocusDepth()
        sp = StimulationPoint(name, itr, pos, z)
        self.ui.pointsParamTree.addParameters(sp.params)
        sp.paramItem = sp.params.items.keys()[0] ## get ahold of the treeWidgetItem, possibly should be a weakref instead
        self.stimPoints.append(sp)
        sp.sigStimPointChanged.connect(self.updatePoints)
        sp.sigTargetDragged.connect(self.targetDragged)
        self.updatePoints()
        return sp.graphicsItem

    def getNextName(self):
        self.counter += 1
        return ("Point", self.counter)

    def activePoints(self):
        ##return a list of active points (ones that are in view and checked)
        return self._activePoints

    def newFrame(self, frame):
        self.lastFrame = frame
        self.updatePoints()

    def targetDragged(self, pt):
        z = self.dev.scopeDevice().getFocusDepth()
        pt.setDepth(z)

    def updatePoints(self):

        self._activePoints = []
        focusDepth = self.dev.scopeDevice().getFocusDepth()

        for pt in self.stimPoints:

            
            pos = self.dev.mapToPrairie(pt.getPos()[:2], self.lastFrame)
            depth = pt.getPos()[2]
            relativeDepth = focusDepth-depth

            ## if point is not in x/y bounds set gray
            if (not 0 < pos[0] < 1) or (not 0 < pos[1] < 1):
                pt.graphicsItem.setEnabledPen(False)
                pt.paramItem.setBackground(0, pg.mkBrush('w'))
                pt.paramItem.setForeground(0, pg.mkBrush((150,150,150)))

            ## if point is not checked set gray
            elif not pt.params.value():
                pt.graphicsItem.setEnabledPen(False)
                pt.paramItem.setBackground(0, pg.mkBrush('w'))

            ## if out-of-focus set point green or red and grey out parameter line
            elif (-10e-6 > relativeDepth) or (relativeDepth > 10e-6):
                pt.graphicsItem.setRelativeDepth(relativeDepth)
                pt.paramItem.setBackground(0, pg.mkBrush('w'))
                pt.paramItem.setForeground(0, pg.mkBrush((150,150,150)))


            elif 0 < pos[0] < 1 and 0 < pos[1] < 1 and pt.params.value() and -10e-6 < relativeDepth < 10e-6:
                pt.graphicsItem.setEnabledPen(True)
                pt.paramItem.setBackground(0, pg.mkBrush('g'))
                pt.paramItem.setForeground(0, pg.mkBrush('k'))
                self._activePoints.append(pt)

            else:
                print('Not sure how to update %s at %s, value %s' %(pt.name, str(pos), pt.params.value()))


    # # def createMarkPointsXML(self):
    #     global baseDicts

    #     baseDicts['PVMarkPointSeriesElements']['Iterations'] = str(self.ui.iterationsSpin.value())
    #     baseDicts['PVMarkPointSeriesElements']['IterationDelay'] = str(self.ui.iterDelaySpin.value())

    #     baseDicts['PVMarkPointElement']['UncagingLaserPower'] = self.spiralParams['laser power']/53. ## convert from %max to voltage

    #     pts = self.activePoints()
    #     baseDicts['PVGalvoPointElement']['Indices'] = "1-%i" % (len(pts))

    #     pointDicts = []
    #     for i, pt in enumerate(pts):
    #         pos = self.mapToPrairie(pt.getPos())
    #         d = {}
    #         d['Index'] = i+1
    #         d['X'] = pos[0]
    #         d['Y'] = pos[1]
    #         d['IsSpiral'] = True
    #         size = self.spiralParams['size']
    #         pSize = self.mapToPrairie((size, size))
    #         d['SpiralWidth'] = pSize[0]
    #         d['SpiralHeight'] = pSize[1]
    #         pointDicts.append(d)

    #     seriesElement = et.Element('PVMarkPointSeriesElements')
    #     for k,v in baseDicts['PVMarkPointSeriesElements'].iteritems():
    #         seriesElement.set(k,str(v))
    #     mpElement = et.SubElement(seriesElement, 'PVMarkPointElement')
    #     for k, v in baseDicts['PVMarkPointElement'].iteritems():
    #         mpElement.set(k,str(v))
    #     galvoElement = et.SubElement(mpElement, 'PVGalvoPointElement')
    #     for k, v in baseDicts['PVGalvoPointElement'].iteritems():
    #         galvoElement.set(k, str(v))
    #     for pt in pointDicts:
    #         ptElement = et.SubElement(galvoElement, 'Point')
    #         for k, v in pt.iteritems():
    #             ptElement.set(k,str(v))

    #     return et.ElementTree(seriesElement)

    def getStimulationCmds(self, pts):
        ## return a list of dicts with per point info that Prairie needs
        frame = self.parent().window().interface.lastFrame
        cmds = []
        for p in pts:
            d = {}
            d['pos'] = self.dev.mapToPrairie(p.getPos(), frame)
            d['duration'] = self.spiralParams['duration'] * 1000 ## convert to ms for prairie
            d['laserPower'] = self.spiralParams['laser power'] ## can leave this as percent
            d['spiralSize'] = self.dev.spiralSizeToPrairie(self.spiralParams['size'], frame)
            d['spiralRevolutions'] = self.spiralParams['spiral revolutions']
            cmds.append(d)
        return cmds

    #frame = man.getModule('PrairieViewStimulator').window().interface.lastFrame

    # def stimulate(self, pt):
    #     pos = mapToPrairie(pt.getPos())
    #     laserPower = self.spiralParams['laser power']
    #     size = self.spiralParams['size']
    #     spiralSize = self.mapToPrairie((size, size))[0]
    #     revolutions = self.spiralParams['spiral revolutions']
    #     duration = self.spiralParams['duration']*1000
    #     self.dev.stimulate(pos, laserPower, duration, spiralSize, revolutions)





class Photostimulation():

    def __init__(self, stimPoint, laserPower, laserDuration, shape):
        self.stimPoint = stimPoint
        self.pos = self.stimPoint.getPos()
        self.laserPower = laserPower
        self.laserDuration = laserDuration
        self.shape = shape






class StimulationPoint(QtCore.QObject):

    sigStimPointChanged = QtCore.Signal(object)
    sigTargetDragged = QtCore.Signal(object)

    def __init__(self, name, itr, pos, z):
        QtCore.QObject.__init__(self)
        self.name = "%s %i" % (name, itr)
        self.z = z
        self.graphicsItem = PhotostimTarget(pos, label=itr)
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=False, renamable=True)

        self.params.sigValueChanged.connect(self.changed)
        self.graphicsItem.sigDragged.connect(self.targetDragged)


    def changed(self, param):
        self.sigStimPointChanged.emit(self)

    def targetDragged(self):
        self.sigTargetDragged.emit(self)

    def setDepth(self, z):
        self.z = z
        self.changed(z)

    def getPos(self):
        ## return position in global coordinates
        return (self.graphicsItem.pos().x(), self.graphicsItem.pos().y(), self.z)




class PhotostimTarget(TargetItem):
    ## inherits from TargetItem, GraphicsObject, GraphicsItem, QGraphicsObject

    def __init__(self, pos, label):
        self.enabledPen = pg.mkPen((0, 255, 255))
        self.disabledPen = pg.mkPen((150,150,150))
        self.enabledBrush = pg.mkBrush((0,0,255,100))
        self.disabledBrush = pg.mkBrush((0,0,255,0))
        TargetItem.__init__(self, pen=self.enabledPen, brush=self.enabledBrush)

        self.setLabel(str(label))
        self.setPos(pg.Point(pos)) 

    def setEnabledPen(self, b):
        if b:
            self.pen = self.enabledPen
            self.brush = self.enabledBrush
        else:
            self.pen = self.disabledPen
            self.brush = self.disabledBrush

        self._picture = None
        self.update()

    def setRelativeDepth(self, depth):
        # adjust the apparent depth of the target
        dist = depth * 255 / 50e-6
        color = (np.clip(dist+256, 0, 255), np.clip(256-dist, 0, 255), 0, 150)
        self.pen = pg.mkPen(color)
        self._picture = None
        self.update()
