from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from PyQt4 import QtGui, QtCore
import moduleTemplate
import pyqtgraph as pg
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
#from acq4.util.generator.SeqParamSet import SeqParameter ## too annoying, just copy/paste and adjust our own
from acq4.pyqtgraph.graphicsItems.TargetItem import TargetItem
import xml.etree.ElementTree as et
#from acq4.util.PrairieView import PrairieView
import os
from collections import OrderedDict
import numpy as np
import acq4.util.units as units
import json


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
        self.pv.markPoints(params['pos'], params['laserPower'], params['duration'], params['spiralSize'], params['spiralRevolutions'], params['nPulses'], params['intervals'])



class PrairiePhotostimModGui(QtGui.QWidget):
    def __init__(self, dev, parent):
        QtGui.QWidget.__init__(self, parent)

        self.dev = dev
        self.ui = moduleTemplate.Ui_Form()
        self.ui.setupUi(self)

        self.spiralParams = pTypes.GroupParameter(name="SpiralParameters", type='group', removable=False, renamable=False, children=[
            dict(name='spiral revolutions', type='float', value='5.0', bounds=[0, None], step=1),
            #dict(name='laser power', type='int', value=0, bounds=[0, 100], step=1),
            #dict(name='duration', type='float', value=0.01, bounds=[0, None], suffix='s', siPrefix=True, step=1e-3),
            dict(name='size', type='float', value=10e-6, bounds=[0, None], suffix='m', siPrefix=True, step=1e-6),
            dict(name='number of stimuli', type='int', value=1, bounds=[1, None])
            ])

        self.ui.stimulusParamTree.addParameters(self.spiralParams)
        self.laserPowerParam = SeqParameter(name='laser_power')
        self.laserDurationParam = SeqParameter(name='pulse_duration')
        self.intervalParam = SeqParameter(name='interpulse_interval')

        for name in ['default', 'start', 'stop']:
            for p in [self.laserDurationParam, self.intervalParam]:
                p.param(name).setOpts(siPrefix=True, suffix='s', limits=[0, None])
                print name, p
            self.laserPowerParam.param(name).setOpts(limits=[0,100])
        self.laserDurationParam.param('default').setOpts(value=0.01)


        self.ui.stimulusParamTree.addParameters(self.laserPowerParam)
        self.ui.stimulusParamTree.addParameters(self.laserDurationParam)
        self.ui.stimulusParamTree.addParameters(self.intervalParam)

        self.stimPoints = []
        self.counter = 0
        self.lastFrame = None
        self.ui.markPointsBtn.setEnabled(False)

        self.parent().prairieImagerDevice.sigNewFrame.connect(self.newFrame)
        self.dev.scopeDevice().sigGlobalTransformChanged.connect(self.updatePoints)

        self.cacheFile = os.path.join(os.path.dirname(__file__), 'photostimulationPoints_temp.cache')


    def addStimPoint(self, pos, stimulationPoint=None):
        name, itr = self.getNextName()
        z = self.dev.scopeDevice().getFocusDepth()
        if stimulationPoint == None:
            sp = StimulationPoint(name, itr, pos, z)
        else:
            sp = stimulationPoint
        self.ui.pointsParamTree.addParameters(sp.params)
        sp.paramItem = sp.params.items.keys()[0] ## get ahold of the treeWidgetItem, possibly should be a weakref instead
        self.stimPoints.append(sp)
        sp.sigStimPointChanged.connect(self.updatePoints)
        sp.sigTargetDragged.connect(self.targetDragged)
        self.updatePoints()
        return sp.graphicsItem

    def clearPoints(self):
        self.ui.pointsParamTree.clear()
        for pt in self.stimPoints:
            pt.graphicsItem.scene().removeItem(pt.graphicsItem)

        self.stimPoints = []
        self.counter = 0

    def getNextName(self):
        self.counter += 1
        return ("Point", self.counter)

    def activePoints(self):
        ##return a list of active points (ones that are in view and checked)
        return self._activePoints

    def newFrame(self, frame):
        self.ui.markPointsBtn.setEnabled(True)
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

        if len(self.stimPoints) > 0: # don't overwrite cache when we reopen the module and load an image
            self.saveCache()

    def saveCache(self):

        pts = []
        for pt in self.stimPoints:
            pts.append((pt.id, pt.getPos()))

        with open(self.cacheFile, 'wb') as f:
            f.write(json.dumps(pts))

    def reloadCache(self, view=None):
        if self.lastFrame is None:
            raise Exception("Cannot load points without frame from PrairieImager for reference.")

        with open(self.cacheFile, 'rb') as f:
            pts = json.loads(f.read())

        try:
            self.clearPoints()
            for pt in pts:
                id, pos = pt
                point = StimulationPoint('Point', id, pos[:-1], pos[-1])
                self.addStimPoint(pos[:-1], point)
                if view is not None:
                    view.addItem(point.graphicsItem)
        except:
            ## rewrite points into cache file so we don't lose them if there was an error in reloading them
            with open(self.cacheFile, 'wb') as f:
                f.write(json.dumps(pts))
            raise



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

    def getStimulationCmd(self, pt):
        ## return a list of dicts with per point info that Prairie needs
        frame = self.parent().window().interface.lastFrame
        d = {}
        d['pos'] = self.dev.mapToPrairie(pt.getPos(), frame)
        d['spiralSize'] = self.dev.spiralSizeToPrairie(self.spiralParams['size'], frame)
        d['spiralRevolutions'] = self.spiralParams['spiral revolutions']
        n = self.spiralParams['number of stimuli']
        d['nPulses'] = n

        durations = self.laserDurationParam.compile()
        powers = self.laserPowerParam.compile()
        intervals = self.intervalParam.compile()

        ## generate lists of sequence commands, multiply times by 1000 to convert from s to ms
        if len(intervals[1]) > 0:
            d['intervals'] = list(np.array(intervals[1]) * 1000)
        else:
            d['intervals'] = [intervals[0]*1000] * (n-1)

        if len(durations[1]) > 0:
            d['duration'] = list(np.array(durations[1]) * 1000)
        else:
            d['duration'] = [durations[0]*1000] * n

        if len(powers[1]) > 0:
            d['laserPower'] = list(powers[1])
        else:
            d['laserPower'] = [powers[0]] * n

        ## check lists of sequence commands
        if len(d['intervals']) != n-1:
            raise Exception("Number of interpulse intervals (%i) must be one less than number of stimuli (%i)"%(len(d['intervals'], n)))
        if len(d['duration']) != n:
            raise Exception("Number of specified durations (%i) must equal number of stimuli (%i)"%(len(d['duration'], n)))
        if len(d['laserPower']) != n:
            raise Exception("Number of specified laser powers (%i) must equal number of stimuli (%i)" %(len(d['laserPower']), n))

        for i, x in enumerate(d['duration'][:-1]):
            if x > d['intervals'][i]:
                raise Exception("Can't have a duration (%f) longer that an interpulse interval (%f)."% (x, d['intervals'][i]))

        return d




class Photostimulation():
    """A data modelling class that represents a single focal photostimulation."""

    def __init__(self, info, id):
        self._info = info
        self.id = id

    def __getattr__(self, name):
        return self._info[name]






class StimulationPoint(QtCore.QObject):

    sigStimPointChanged = QtCore.Signal(object)
    sigTargetDragged = QtCore.Signal(object)

    def __init__(self, name, itr, pos, z):
        QtCore.QObject.__init__(self)
        self.name = "%s %i" % (name, itr)
        self.id = itr
        self.z = z
        self.graphicsItem = PhotostimTarget(pos, label=itr)
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=False, renamable=True)

        self.params.sigValueChanged.connect(self.changed)
        self.graphicsItem.sigDragged.connect(self.targetDragged)

#        self.positionHistory = []
        self.stimulations = []


    def changed(self, param):
        self.sigStimPointChanged.emit(self)

    def targetDragged(self):
#        self.updateHistory()
        self.sigTargetDragged.emit(self)

    def setDepth(self, z):
        self.z = z
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



class PhotostimTarget(TargetItem):
    ## inherits from TargetItem, GraphicsObject, GraphicsItem, QGraphicsObject
    sigClicked = QtCore.Signal(object)

    def __init__(self, pos, label, **opts):
        self.enabledPen = pg.mkPen((0, 255, 255))
        self.disabledPen = pg.mkPen((150,150,150))
        self.enabledBrush = pg.mkBrush((0,0,255,100))
        self.disabledBrush = pg.mkBrush((0,0,255,0))
        TargetItem.__init__(self, pen=self.enabledPen, brush=self.enabledBrush, **opts)

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

    def mouseClickEvent(self, ev):
        ev.accept()
        self.sigClicked.emit(self)

class SeqParameter(pTypes.GroupParameter):
    def __init__(self, **args):
        
        self.evalLocals = units.allUnits.copy()
        #exec('from numpy import *', self.evalLocals)  ## import all of numpy into the eval namespace
        
        args['renamable'] = False
        args['removable'] = False
        args['name'] = args.get('name', 'Param')
        args['autoIncrementName'] = False
        args['strictNaming'] = True
        
        args['children'] = [
            {'name': 'default', 'type': 'float', 'value': 0},
            {'name': 'sequence', 'type': 'list', 'value': 'off', 'values': ['off', 'range', 'list']},
            {'name': 'start', 'type': 'float', 'value': 0, 'visible': False}, 
            {'name': 'stop', 'type': 'float', 'value': 0, 'visible': False}, 
            {'name': 'steps', 'type': 'int', 'value': 10, 'visible': False},
            {'name': 'log spacing', 'type': 'bool', 'value': False, 'visible': False}, 
            {'name': 'list', 'type': 'str', 'value': '[]', 'visible': False}, 
            {'name': 'randomize', 'type': 'bool', 'value': False, 'visible': False}, 
            #{'name': 'expression', 'type': 'str', 'visible': False},
        ]
        
        pTypes.GroupParameter.__init__(self, **args)
        #self.sequence.sigValueChanged.connect(self.seqChanged)
        
        self.visibleParams = {  ## list of params to display in each mode
            'off': ['default', 'sequence'],
            'range': ['default', 'sequence', 'start', 'stop', 'steps', 'log spacing', 'randomize'],
            'list': ['default', 'sequence', 'list', 'randomize'],
            #'eval': ['default', 'sequence', 'expression']
        }
        
        
    def treeStateChanged(self, param, changes):
        ## catch changes to 'sequence' so we can hide/show other params.
        ## Note: it would be easier to just catch self.sequence.sigValueChanged,
        ## but this approach allows us to block tree change events so they are all
        ## released as a single update.
        with self.treeChangeBlocker():
            ## queue up change 
            pTypes.GroupParameter.treeStateChanged(self, param, changes)
            
            ## if needed, add some more changes before releasing the signal
            for param, change, data in changes:
                ## if the sequence value changes, hide/show other parameters
                if param is self.param('sequence') and change == 'value':
                    vis = self.visibleParams[self['sequence']]
                    for ch in self:
                        if ch.name() in vis:
                            ch.show()
                        else:
                            ch.hide()
    #def seqChanged(self):
        #with self.treeChangeBlocker():
            #vis = self.visibleParams[self['sequence']]
            #for ch in self:
                #if ch.name() in vis:
                    #ch.show()
                #else:
                    #ch.hide()
        
    def compile(self):
        name = self.name()
        #default = self.evalStr('default')
        default = self['default']
        mode = self['sequence']
        if mode == 'off':
            seq = []
        elif mode == 'range':
            #start = self.evalStr('start')
            #stop = self.evalStr('stop')
            start = self['start']
            stop = self['stop']
            nPts = self['steps']
            if self['log spacing']:
                seq = fn.logSpace(start, stop, nPts)
            else:
                seq = np.linspace(start, stop, nPts)
        elif mode == 'list':
            seq = list(self.evalStr('list'))
        elif mode == 'eval':
            seq = self.evalStr('expression')
        else:
            raise Exception('Unknown sequence mode %s' % mode)
        
        if self['randomize']:
            np.random.shuffle(seq)
        
        ## sanity check
        try:
            len(seq)
        except:
            raise Exception("Parameter %s generated invalid sequence: %s" % (name, str(seq)))
        
        return default, seq

    def evalStr(self, name):
        try:
            s = eval(self[name], self.evalLocals)
        except:
            raise Exception("Can't evaluate %s, %s"%(str(name), self[name]))
        return s
        
    def setState(self, state):
        for k in state:
            self[k] = state[k]
            self.param(k).setDefault(state[k])
        
    def getState(self):
        state = collections.OrderedDict()
        for ch in self:
            if not ch.opts['visible']:
                continue
            name = ch.name()
            val = ch.value()
            if val is False:
                continue
            state[name] = val
        return state
