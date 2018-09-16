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


    def addStimPoint(self, pos):
        name, itr = self.getNextName()
        sp = StimulationPoint(name, itr, pos)
        self.ui.pointsParamTree.addParameters(sp.params)
        self.stimPoints.append(sp)
        return sp.graphicsItem

    def getNextName(self):
        self.counter += 1
        return ("Point", self.counter)

    def activePoints(self):
        ##return a list of active points (ones that are in view and checked)
        return [sp for sp in self.stimPoints if sp.params.value() == True]

    def newFrame(self, frame):
        ### check if stimulationPoints are within new frame, deactivate them if not
        for sp in self.stimPoints:
            if 0 < self.dev.mapToPrairie(sp.getPos()) < 1:
                sp.params.setValue(True)
            else: 
                sp.params.setValue(False)

    def createMarkPointsXML(self):
        global baseDicts

        baseDicts['PVMarkPointSeriesElements']['Iterations'] = str(self.ui.iterationsSpin.value())
        baseDicts['PVMarkPointSeriesElements']['IterationDelay'] = str(self.ui.iterDelaySpin.value())

        baseDicts['PVMarkPointElement']['UncagingLaserPower'] = self.spiralParams['laser power']/53. ## convert from %max to voltage

        pts = self.activePoints()
        baseDicts['PVGalvoPointElement']['Indices'] = "1-%i" % (len(pts))

        pointDicts = []
        for i, pt in enumerate(pts):
            pos = self.mapToPrairie(pt.getPos())
            d = {}
            d['Index'] = i+1
            d['X'] = pos[0]
            d['Y'] = pos[1]
            d['IsSpiral'] = True
            size = self.spiralParams['size']
            pSize = self.mapToPrairie((size, size))
            d['SpiralWidth'] = pSize[0]
            d['SpiralHeight'] = pSize[1]
            pointDicts.append(d)

        seriesElement = et.Element('PVMarkPointSeriesElements')
        for k,v in baseDicts['PVMarkPointSeriesElements'].iteritems():
            seriesElement.set(k,str(v))
        mpElement = et.SubElement(seriesElement, 'PVMarkPointElement')
        for k, v in baseDicts['PVMarkPointElement'].iteritems():
            mpElement.set(k,str(v))
        galvoElement = et.SubElement(mpElement, 'PVGalvoPointElement')
        for k, v in baseDicts['PVGalvoPointElement'].iteritems():
            galvoElement.set(k, str(v))
        for pt in pointDicts:
            ptElement = et.SubElement(galvoElement, 'Point')
            for k, v in pt.iteritems():
                ptElement.set(k,str(v))

        return et.ElementTree(seriesElement)

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






class StimulationPoint():

    def __init__(self, name, itr, pos):

        self.name = "%s %i" % (name, itr)
        self.graphicsItem = PhotostimTarget(pos, label=itr)
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True)

        self.params.sigValueChanged.connect(self.valueChanged)

    def valueChanged(self, b):
        self.graphicsItem.setEnabledPen(b)

    def getPos(self):
        ## return position in global coordinates
        return self.graphicsItem.pos()


class PhotostimTarget(TargetItem):

    def __init__(self, pos, label):
        self.enabledPen = pg.mkPen((0, 255, 255))
        self.disabledPen = pg.mkPen((150,150,150))
        TargetItem.__init__(self, pen=self.enabledPen)

        self.setLabel(str(label))
        self.setPos(pg.Point(pos)) 

    def setEnabledPen(self, b):
        if b:
            self.pen = self.enabledPen
        else:
            self.pen = self.disabledPen
